from __future__ import annotations

from uuid import UUID

from starlette.requests import Request
from starlette.responses import RedirectResponse

from aimg.admin.audit import log_action
from aimg.admin.decorators import require_role
from aimg.admin.pagination import get_page_info
from aimg.db.repos.job_types import JobTypeRepo
from aimg.db.repos.providers import ProviderRepo


@require_role("super_admin", "admin")
async def job_type_list(request: Request):
    templates = request.app.state.templates
    db_pool = request.app.state.db_pool
    repo = JobTypeRepo(db_pool)

    page = int(request.query_params.get("page", 1))
    total = await repo.count_all()
    page_info = get_page_info(page, total)
    job_types = await repo.list_all_admin(
        limit=page_info["per_page"], offset=page_info["offset"],
    )

    ctx = {"job_types": job_types, "page_info": page_info}

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "job_types/_rows.html", ctx)
    return templates.TemplateResponse(request, "job_types/list.html", ctx)


@require_role("super_admin", "admin")
async def job_type_detail(request: Request):
    templates = request.app.state.templates
    db_pool = request.app.state.db_pool
    jt_id = UUID(str(request.path_params["id"]))

    jt_repo = JobTypeRepo(db_pool)
    job_type = await jt_repo.get_by_id(jt_id)
    if not job_type:
        return RedirectResponse("/admin/job-types", status_code=302)

    providers_chain = await jt_repo.get_providers_for_job_type(jt_id)

    # Load provider details
    provider_repo = ProviderRepo(db_pool)
    all_providers = await provider_repo.list_all(limit=100)
    provider_map = {p.id: p for p in all_providers}

    return templates.TemplateResponse(request, "job_types/detail.html", {
        "job_type": job_type,
        "providers_chain": providers_chain,
        "provider_map": provider_map,
        "all_providers": all_providers,
    })


@require_role("super_admin")
async def job_type_update(request: Request):
    jt_id = UUID(str(request.path_params["id"]))
    form = await request.form()

    kwargs = {}
    if form.get("credit_cost") is not None:
        kwargs["credit_cost"] = int(form["credit_cost"])
    if form.get("timeout_seconds") is not None:
        kwargs["timeout_seconds"] = int(form["timeout_seconds"])
    if form.get("status"):
        kwargs["status"] = form["status"]

    jt_repo = JobTypeRepo(request.app.state.db_pool)
    await jt_repo.update(jt_id, **kwargs)
    await log_action(request, "job_type.update", "job_type", jt_id, kwargs)
    return RedirectResponse(f"/admin/job-types/{jt_id}", status_code=302)


@require_role("super_admin")
async def job_type_provider_add(request: Request):
    jt_id = UUID(str(request.path_params["id"]))
    form = await request.form()
    provider_id = UUID(form["provider_id"])
    priority = int(form.get("priority", 0))

    jt_repo = JobTypeRepo(request.app.state.db_pool)
    await jt_repo.add_provider(jt_id, provider_id, priority=priority)
    await log_action(
        request, "job_type.update_chain", "job_type", jt_id,
        {"provider_id": str(provider_id), "priority": priority, "action": "add"},
    )
    return RedirectResponse(f"/admin/job-types/{jt_id}", status_code=302)


@require_role("super_admin")
async def job_type_provider_remove(request: Request):
    jt_id = UUID(str(request.path_params["jt_id"]))
    provider_id = UUID(str(request.path_params["p_id"]))

    jt_repo = JobTypeRepo(request.app.state.db_pool)
    await jt_repo.remove_provider(jt_id, provider_id)
    await log_action(
        request, "job_type.update_chain", "job_type", jt_id,
        {"provider_id": str(provider_id), "action": "remove"},
    )
    return RedirectResponse(f"/admin/job-types/{jt_id}", status_code=302)
