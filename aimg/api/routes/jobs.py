from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel

from aimg.api.dependencies import (
    get_current_user,
    get_db_pool,
    get_redis,
    get_s3_client,
    get_settings,
)
from aimg.api.envelope import ApiResponse
from aimg.api.errors import (
    ForbiddenError,
    InsufficientCreditsError,
    InvalidInputError,
    InvalidJobTypeError,
    NotFoundError,
    RateLimitedError,
)
from aimg.common.logging import request_id_var
from aimg.common.settings import Settings
from aimg.db.models import Job, JobType, User
from aimg.db.repos.files import FileRepo
from aimg.db.repos.job_types import JobTypeRepo
from aimg.db.repos.jobs import JobRepo
from aimg.services.billing import reserve_credits
from aimg.services.rate_limit import check_user_jobs_per_hour

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])

QUEUE_KEY = "aimg:jobs:queue"


class CreateJobRequest(BaseModel):
    job_type: str
    input: dict
    language: str = "en"


def _build_job_response(job: Job, job_type: JobType) -> dict:
    data = {
        "job_id": str(job.id),
        "status": job.status,
        "job_type": job_type.slug,
        "credit_cost": job.credit_charged,
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
    return data


@router.post("", status_code=201)
async def create_job(
    body: CreateJobRequest,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    redis_client: aioredis.Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    # Set language on request state for error handler
    request.state.language = body.language

    jt_repo = JobTypeRepo(db_pool)
    job_type = await jt_repo.get_by_slug(body.job_type)
    if not job_type:
        raise InvalidJobTypeError(f"Unknown job type: {body.job_type}")
    if job_type.status != "active":
        raise InvalidJobTypeError(f"Job type '{body.job_type}' is not active")

    # Idempotency check
    if idempotency_key:
        idem_redis_key = f"aimg:idempotency:{user.integration_id}:{idempotency_key}"
        existing_job_id = await redis_client.get(idem_redis_key)
        if existing_job_id:
            job_repo = JobRepo(db_pool)
            existing_job = await job_repo.get_by_id(UUID(existing_job_id))
            if existing_job:
                rid = request_id_var.get() or ""
                response.status_code = 200
                return ApiResponse(
                    request_id=rid,
                    success=True,
                    data=_build_job_response(existing_job, job_type),
                ).model_dump(mode="json")
            # Job in Redis but not in DB — stale key, delete and proceed
            await redis_client.delete(idem_redis_key)

    # Per-user rate limit
    allowed, limit, remaining, reset_ts = await check_user_jobs_per_hour(
        redis_client, user.id, settings.user_rate_limit_jobs_per_hour
    )
    if not allowed:
        raise RateLimitedError(
            retry_after=max(1, reset_ts - int(time.time())),
            details={"limit": limit, "window": "1 hour"},
        )

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
            details={
                "required": job_type.credit_cost,
                "available": total,
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
                idempotency_key=idempotency_key,
                conn=conn,
            )
            await reserve_credits(
                db_pool, conn, user.id, job_type.credit_cost, job.id
            )

    # Save idempotency key
    if idempotency_key:
        idem_redis_key = f"aimg:idempotency:{user.integration_id}:{idempotency_key}"
        await redis_client.setex(idem_redis_key, 86400, str(job.id))

    # Enqueue
    await redis_client.lpush(QUEUE_KEY, str(job.id))

    rid = request_id_var.get() or ""
    return ApiResponse(
        request_id=rid,
        success=True,
        data=_build_job_response(job, job_type),
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

    rid = request_id_var.get() or ""
    if job_type:
        data = _build_job_response(job, job_type)
    else:
        data = _build_job_response(job, JobType(
            id=job.job_type_id, slug=str(job.job_type_id), name="unknown",
            input_schema={}, output_schema={}, credit_cost=0,
            timeout_seconds=0, status="unknown",
            created_at=job.created_at, updated_at=job.updated_at,
        ))
    return ApiResponse(
        request_id=rid,
        success=True,
        data=data,
    ).model_dump(mode="json")


@router.get("/{job_id}/result")
async def get_job_result(
    job_id: UUID,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    s3_client: object = Depends(get_s3_client),
    settings: Settings = Depends(get_settings),
) -> dict:
    job_repo = JobRepo(db_pool)
    job = await job_repo.get_by_id(job_id)
    if not job:
        raise NotFoundError("Job not found")
    if job.integration_id != user.integration_id:
        raise ForbiddenError("Access denied to this job")
    if job.status != "succeeded":
        raise InvalidInputError(
            "Job has not succeeded yet",
            details={"status": job.status},
        )

    output = job.output_data or {}
    file_id_str = output.get("image")
    if not file_id_str:
        raise NotFoundError("No output file found")

    file_repo = FileRepo(db_pool)
    file_record = await file_repo.get_by_id(UUID(file_id_str))
    if not file_record:
        raise NotFoundError("Output file not found")

    download_url = await s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": file_record.s3_bucket, "Key": file_record.s3_key},
        ExpiresIn=settings.s3_presign_ttl,
    )
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.s3_presign_ttl)

    rid = request_id_var.get() or ""
    return ApiResponse(
        request_id=rid,
        success=True,
        data={
            "job_id": str(job.id),
            "file_id": file_id_str,
            "download_url": download_url,
            "content_type": file_record.content_type,
            "size_bytes": file_record.size_bytes,
            "expires_at": expires_at.isoformat(),
        },
    ).model_dump(mode="json")
