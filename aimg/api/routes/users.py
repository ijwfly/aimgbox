from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, Query

from aimg.api.dependencies import get_current_user, get_db_pool
from aimg.api.envelope import ApiResponse
from aimg.common.logging import request_id_var
from aimg.common.pagination import clamp_limit, decode_cursor, encode_cursor
from aimg.db.models import User
from aimg.db.repos.job_types import JobTypeRepo
from aimg.db.repos.jobs import JobRepo

router = APIRouter(prefix="/v1/users", tags=["users"])


@router.get("/me/balance")
async def get_balance(
    user: User = Depends(get_current_user),
) -> dict:
    rid = request_id_var.get() or ""
    return ApiResponse(
        request_id=rid,
        success=True,
        data={
            "external_user_id": user.external_user_id,
            "free_credits": user.free_credits,
            "paid_credits": user.paid_credits,
            "total_credits": user.free_credits + user.paid_credits,
        },
    ).model_dump(mode="json")


@router.get("/me/history")
async def get_history(
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    cursor: str | None = Query(None),
    limit: int | None = Query(None, ge=1, le=100),
    status: str | None = Query(None),
    job_type: str | None = Query(None),
) -> dict:
    real_limit = clamp_limit(limit)

    cursor_created_at = None
    cursor_id = None
    if cursor:
        cursor_created_at, cursor_id = decode_cursor(cursor)

    job_repo = JobRepo(db_pool)
    jobs = await job_repo.list_for_user(
        user.id,
        user.integration_id,
        limit=real_limit + 1,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
        status_filter=status,
        job_type_filter=job_type,
    )

    has_more = len(jobs) > real_limit
    if has_more:
        jobs = jobs[:real_limit]

    jt_repo = JobTypeRepo(db_pool)
    jt_cache: dict = {}

    items = []
    for job in jobs:
        if job.job_type_id not in jt_cache:
            jt = await jt_repo.get_by_id(job.job_type_id)
            jt_cache[job.job_type_id] = jt
        jt = jt_cache[job.job_type_id]

        items.append({
            "job_id": str(job.id),
            "status": job.status,
            "job_type": jt.slug if jt else str(job.job_type_id),
            "credit_charged": job.credit_charged,
            "created_at": job.created_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        })

    next_cursor = None
    if has_more and jobs:
        last = jobs[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    rid = request_id_var.get() or ""
    return ApiResponse(
        request_id=rid,
        success=True,
        data={
            "jobs": items,
            "next_cursor": next_cursor,
            "has_more": has_more,
        },
    ).model_dump(mode="json")
