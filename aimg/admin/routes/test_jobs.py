from __future__ import annotations

from uuid import UUID

import httpx
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from aimg.admin.audit import log_action
from aimg.admin.decorators import require_role
from aimg.db.repos.job_types import JobTypeRepo


def _schema_to_fields(schema: dict) -> list[dict]:
    """Convert JSON Schema properties to template-friendly field descriptors."""
    fields: list[dict] = []
    required = set(schema.get("required", []))
    for name, prop in schema.get("properties", {}).items():
        field: dict = {
            "name": name,
            "label": name.replace("_", " ").title(),
            "required": name in required,
        }
        if prop.get("format") == "uuid":
            field["type"] = "file"
        elif "enum" in prop:
            field["type"] = "select"
            field["options"] = prop["enum"]
            field["default"] = prop.get("default")
        elif prop.get("type") == "integer":
            field["type"] = "number"
            field["default"] = prop.get("default")
            field["min"] = prop.get("minimum")
            field["max"] = prop.get("maximum")
        elif prop.get("type") == "string":
            if "prompt" in name:
                field["type"] = "textarea"
            else:
                field["type"] = "text"
                field["default"] = prop.get("default", "")
        else:
            field["type"] = "text"
            field["default"] = prop.get("default", "")
        fields.append(field)
    return fields


@require_role("super_admin", "admin")
async def test_job_form(request: Request):
    templates = request.app.state.templates
    db_pool = request.app.state.db_pool

    jt_repo = JobTypeRepo(db_pool)
    job_types = await jt_repo.list_active()

    return templates.TemplateResponse(request, "test_jobs/form.html", {
        "job_types": job_types,
    })


@require_role("super_admin", "admin")
async def test_job_fields(request: Request):
    templates = request.app.state.templates
    db_pool = request.app.state.db_pool

    slug = request.query_params.get("job_type", "")
    if not slug:
        return HTMLResponse("")

    jt_repo = JobTypeRepo(db_pool)
    job_type = await jt_repo.get_by_slug(slug)
    if not job_type:
        return HTMLResponse("<p>Unknown job type</p>")

    fields = _schema_to_fields(job_type.input_schema)
    return templates.TemplateResponse(request, "test_jobs/_fields.html", {
        "fields": fields,
    })


@require_role("super_admin", "admin")
async def test_job_create(request: Request):
    templates = request.app.state.templates
    db_pool = request.app.state.db_pool
    settings = request.app.state.settings

    form = await request.form()
    api_key = form.get("api_key", "").strip()
    external_user_id = form.get("external_user_id", "").strip()
    job_type_slug = form.get("job_type", "").strip()

    # Reload job types for re-render on error
    jt_repo = JobTypeRepo(db_pool)
    job_types = await jt_repo.list_active()

    def _form_error(msg: str, status: int = 400):
        return templates.TemplateResponse(request, "test_jobs/form.html", {
            "job_types": job_types,
            "error": msg,
            "api_key": api_key,
            "external_user_id": external_user_id,
        }, status_code=status)

    if not api_key or not external_user_id or not job_type_slug:
        return _form_error("API Key, External User ID, and Job Type are required")

    job_type = await jt_repo.get_by_slug(job_type_slug)
    if not job_type:
        return _form_error(f"Unknown job type: {job_type_slug}")

    api_url = settings.api_internal_url.rstrip("/")
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": external_user_id,
    }

    fields = _schema_to_fields(job_type.input_schema)
    file_field_names = {f["name"] for f in fields if f["type"] == "file"}
    input_data: dict = {}

    async with httpx.AsyncClient(timeout=30) as client:
        # Upload files first
        for field_name in file_field_names:
            upload = form.get(field_name)
            if not upload or not hasattr(upload, "read"):
                if field_name in {f["name"] for f in fields if f["required"]}:
                    return _form_error(f"File is required for '{field_name}'")
                continue

            content = await upload.read()
            if not content:
                continue

            content_type = upload.content_type or "application/octet-stream"
            filename = upload.filename or "upload"

            resp = await client.post(
                f"{api_url}/v1/files",
                headers=headers,
                files={"file": (filename, content, content_type)},
            )
            if resp.status_code != 201:
                error_msg = _extract_api_error(resp)
                return _form_error(f"File upload failed: {error_msg}")
            file_id = resp.json()["data"]["file_id"]
            input_data[field_name] = file_id

        # Collect non-file fields
        for field in fields:
            if field["name"] in file_field_names:
                continue
            val = form.get(field["name"], "")
            if isinstance(val, str):
                val = val.strip()
            if val:
                if field["type"] == "number":
                    input_data[field["name"]] = int(val)
                else:
                    input_data[field["name"]] = val
            elif field.get("default") is not None and field["default"] != "":
                input_data[field["name"]] = field["default"]

        # Create job
        resp = await client.post(
            f"{api_url}/v1/jobs",
            headers=headers,
            json={"job_type": job_type_slug, "input": input_data},
        )
        if resp.status_code not in (200, 201):
            error_msg = _extract_api_error(resp)
            return _form_error(f"Job creation failed: {error_msg}")

        job_data = resp.json()["data"]
        job_id = job_data["job_id"]

    await log_action(
        request, "test_job.create", "job", UUID(job_id),
        {"job_type": job_type_slug},
    )

    return RedirectResponse(
        f"/admin/test-jobs/poll/{job_id}"
        f"?api_key={api_key}&user_id={external_user_id}",
        status_code=302,
    )


@require_role("super_admin", "admin")
async def test_job_poll(request: Request):
    templates = request.app.state.templates
    settings = request.app.state.settings

    job_id = request.path_params["job_id"]
    api_key = request.query_params.get("api_key", "")
    external_user_id = request.query_params.get("user_id", "")

    if not api_key or not external_user_id:
        return HTMLResponse("Missing api_key or user_id", status_code=400)

    api_url = settings.api_internal_url.rstrip("/")
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": external_user_id,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{api_url}/v1/jobs/{job_id}",
            headers=headers,
        )
        if resp.status_code != 200:
            error_msg = _extract_api_error(resp)
            return templates.TemplateResponse(
                request, "test_jobs/result.html", {
                    "job_id": job_id,
                    "status": "error",
                    "error": f"Failed to fetch job: {error_msg}",
                    "api_key": api_key,
                    "user_id": external_user_id,
                },
            )

        job_data = resp.json()["data"]
        status = job_data["status"]

        result_url = None
        if status == "succeeded":
            result_resp = await client.get(
                f"{api_url}/v1/jobs/{job_id}/result",
                headers=headers,
            )
            if result_resp.status_code == 200:
                result_data = result_resp.json()["data"]
                result_url = result_data["download_url"]

    ctx = {
        "job_id": job_id,
        "status": status,
        "job_data": job_data,
        "result_url": result_url,
        "api_key": api_key,
        "user_id": external_user_id,
        "error": job_data.get("error"),
    }

    # For htmx polling requests, return just the partial
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request, "test_jobs/_poll_partial.html", ctx,
        )
    return templates.TemplateResponse(request, "test_jobs/result.html", ctx)


def _extract_api_error(resp: httpx.Response) -> str:
    """Extract human-readable error from API response."""
    try:
        body = resp.json()
        err = body.get("error", {})
        if isinstance(err, dict):
            msg = err.get("message", "")
            code = err.get("code", "")
            if msg:
                return f"{code}: {msg}" if code else msg
        return str(body)
    except Exception:
        return f"HTTP {resp.status_code}: {resp.text[:200]}"
