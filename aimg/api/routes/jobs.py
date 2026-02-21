from __future__ import annotations

from uuid import UUID

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from aimg.api.dependencies import get_current_user, get_db_pool, get_redis
from aimg.api.envelope import ApiResponse
from aimg.api.errors import (
    ForbiddenError,
    InsufficientCreditsError,
    InvalidInputError,
    InvalidJobTypeError,
    NotFoundError,
)
from aimg.common.logging import request_id_var
from aimg.db.models import User
from aimg.db.repos.files import FileRepo
from aimg.db.repos.job_types import JobTypeRepo
from aimg.db.repos.jobs import JobRepo
from aimg.services.billing import reserve_credits

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])

QUEUE_KEY = "aimg:jobs:queue"


class CreateJobRequest(BaseModel):
    job_type: str
    input: dict
    language: str = "en"


@router.post("", status_code=201)
async def create_job(
    body: CreateJobRequest,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    redis_client: aioredis.Redis = Depends(get_redis),
) -> dict:
    jt_repo = JobTypeRepo(db_pool)
    job_type = await jt_repo.get_by_slug(body.job_type)
    if not job_type:
        raise InvalidJobTypeError(f"Unknown job type: {body.job_type}")
    if job_type.status != "active":
        raise InvalidJobTypeError(f"Job type '{body.job_type}' is not active")

    # Validate input file references exist and belong to integration
    file_repo = FileRepo(db_pool)
    for key, val in body.input.items():
        if isinstance(val, str):
            try:
                file_id = UUID(val)
            except ValueError:
                continue
            f = await file_repo.get_by_id(file_id)
            if f and f.integration_id != user.integration_id:
                raise InvalidInputError(
                    f"File {val} does not belong to this integration",
                    details={"field": key},
                )

    # Check credits
    total = user.free_credits + user.paid_credits
    if total < job_type.credit_cost:
        raise InsufficientCreditsError(
            f"Insufficient credits. Required: {job_type.credit_cost}, available: {total}",
            details={
                "required": job_type.credit_cost,
                "free_credits": user.free_credits,
                "paid_credits": user.paid_credits,
            },
        )

    # Transaction: reserve credits + create job
    job_repo = JobRepo(db_pool)
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            job = await job_repo.create(
                integration_id=user.integration_id,
                user_id=user.id,
                job_type_id=job_type.id,
                input_data=body.input,
                credit_charged=job_type.credit_cost,
                language=body.language,
                conn=conn,
            )
            await reserve_credits(
                db_pool, conn, user.id, job_type.credit_cost, job.id
            )

    # Enqueue
    await redis_client.lpush(QUEUE_KEY, str(job.id))

    rid = request_id_var.get() or ""
    return ApiResponse(
        request_id=rid,
        success=True,
        data={
            "job_id": str(job.id),
            "status": job.status,
            "job_type": body.job_type,
            "credit_cost": job_type.credit_cost,
            "created_at": job.created_at.isoformat(),
        },
    ).model_dump(mode="json")


@router.get("/{job_id}")
async def get_job(
    job_id: UUID,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> dict:
    job_repo = JobRepo(db_pool)
    job = await job_repo.get_by_id(job_id)
    if not job:
        raise NotFoundError("Job not found")
    if job.integration_id != user.integration_id:
        raise ForbiddenError("Access denied to this job")

    jt_repo = JobTypeRepo(db_pool)
    job_type = await jt_repo.get_by_id(job.job_type_id)

    data = {
        "job_id": str(job.id),
        "status": job.status,
        "job_type": job_type.slug if job_type else str(job.job_type_id),
        "credit_charged": job.credit_charged,
        "input": job.input_data,
        "output": job.output_data,
        "error": None,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }

    if job.error_code:
        data["error"] = {
            "code": job.error_code,
            "message": job.error_message,
        }

    rid = request_id_var.get() or ""
    return ApiResponse(
        request_id=rid,
        success=True,
        data=data,
    ).model_dump(mode="json")
