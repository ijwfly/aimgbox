from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from starlette.requests import Request

from aimg.admin.csv_export import export_jobs_csv
from aimg.admin.decorators import require_auth
from aimg.admin.pagination import get_page_info
from aimg.db.repos.files import FileRepo
from aimg.db.repos.job_attempts import JobAttemptRepo
from aimg.db.repos.jobs import JobRepo


def _parse_filters(request: Request) -> dict:
    filters = {}
    if request.query_params.get("status"):
        filters["status"] = request.query_params["status"]
    if request.query_params.get("integration_id"):
        filters["integration_id"] = UUID(request.query_params["integration_id"])
    if request.query_params.get("job_type_id"):
        filters["job_type_id"] = UUID(request.query_params["job_type_id"])
    if request.query_params.get("user_id"):
        filters["user_id"] = UUID(request.query_params["user_id"])
    if request.query_params.get("date_from"):
        filters["date_from"] = datetime.fromisoformat(
            request.query_params["date_from"]
        ).replace(tzinfo=UTC)
    if request.query_params.get("date_to"):
        filters["date_to"] = datetime.fromisoformat(
            request.query_params["date_to"]
        ).replace(tzinfo=UTC)
    return filters


@require_auth
async def job_list(request: Request):
    templates = request.app.state.templates
    db_pool = request.app.state.db_pool
    repo = JobRepo(db_pool)

    page = int(request.query_params.get("page", 1))
    filters = _parse_filters(request)

    total = await repo.count(**filters)
    page_info = get_page_info(page, total)
    jobs = await repo.list_all(
        limit=page_info["per_page"], offset=page_info["offset"], **filters,
    )

    ctx = {"jobs": jobs, "page_info": page_info, "filters": request.query_params}

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "jobs/_rows.html", ctx)
    return templates.TemplateResponse(request, "jobs/list.html", ctx)


@require_auth
async def job_detail(request: Request):
    templates = request.app.state.templates
    db_pool = request.app.state.db_pool
    job_id = UUID(str(request.path_params["id"]))

    job_repo = JobRepo(db_pool)
    job = await job_repo.get_by_id(job_id)
    if not job:
        return templates.TemplateResponse(
            request, "jobs/list.html",
            {"jobs": [], "page_info": get_page_info(1, 0),
             "filters": {}, "flash_error": "Job not found"},
            status_code=404,
        )

    attempt_repo = JobAttemptRepo(db_pool)
    attempts = await attempt_repo.list_by_job(job_id)

    # Generate presigned result URL for succeeded jobs
    result_url = None
    if job.status == "succeeded" and job.output_data:
        file_id_str = job.output_data.get("image")
        if file_id_str:
            file_repo = FileRepo(db_pool)
            file_record = await file_repo.get_by_id(UUID(file_id_str))
            if file_record:
                s3_client = request.app.state.s3_client
                settings = request.app.state.settings
                result_url = await s3_client.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": file_record.s3_bucket,
                        "Key": file_record.s3_key,
                    },
                    ExpiresIn=settings.s3_presign_ttl,
                )

    return templates.TemplateResponse(request, "jobs/detail.html", {
        "job": job, "attempts": attempts, "result_url": result_url,
    })


@require_auth
async def job_export(request: Request):
    db_pool = request.app.state.db_pool
    repo = JobRepo(db_pool)
    filters = _parse_filters(request)

    jobs = await repo.list_all(limit=10000, offset=0, **filters)
    return export_jobs_csv(jobs)
