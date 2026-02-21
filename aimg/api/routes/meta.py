from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends

from aimg.api.dependencies import get_current_integration, get_db_pool
from aimg.api.envelope import ApiResponse
from aimg.common.logging import request_id_var
from aimg.db.models import Integration
from aimg.db.repos.job_types import JobTypeRepo

router = APIRouter(prefix="/v1/meta", tags=["meta"])


@router.get("/job-types")
async def list_job_types(
    _integration: Integration = Depends(get_current_integration),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> dict:
    jt_repo = JobTypeRepo(db_pool)
    job_types = await jt_repo.list_active()

    items = [
        {
            "slug": jt.slug,
            "name": jt.name,
            "description": jt.description,
            "credit_cost": jt.credit_cost,
            "timeout_seconds": jt.timeout_seconds,
            "input_schema": jt.input_schema,
            "output_schema": jt.output_schema,
        }
        for jt in job_types
    ]

    rid = request_id_var.get() or ""
    return ApiResponse(
        request_id=rid,
        success=True,
        data={"job_types": items},
    ).model_dump(mode="json")
