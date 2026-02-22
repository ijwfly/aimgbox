from __future__ import annotations

from uuid import UUID

from starlette.requests import Request
from starlette.responses import RedirectResponse

from aimg.admin.audit import log_action
from aimg.admin.decorators import require_auth, require_role
from aimg.admin.pagination import get_page_info
from aimg.db.repos.partners import PartnerRepo


@require_auth
async def partner_list(request: Request):
    templates = request.app.state.templates
    db_pool = request.app.state.db_pool
    repo = PartnerRepo(db_pool)

    page = int(request.query_params.get("page", 1))
    status = request.query_params.get("status")

    total = await repo.count(status=status)
    page_info = get_page_info(page, total)
    partners = await repo.list_all(
        limit=page_info["per_page"], offset=page_info["offset"], status=status,
    )

    ctx = {"partners": partners, "page_info": page_info, "filter_status": status}

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "partners/_rows.html", ctx)
    return templates.TemplateResponse(request, "partners/list.html", ctx)


@require_role("super_admin", "admin")
async def partner_new(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "partners/form.html")


@require_role("super_admin", "admin")
async def partner_create(request: Request):
    form = await request.form()
    name = form.get("name", "").strip()
    if not name:
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request, "partners/form.html", {"error": "Name is required"}, status_code=400
        )

    repo = PartnerRepo(request.app.state.db_pool)
    partner = await repo.create(name)
    await log_action(request, "partner.create", "partner", partner.id, {"name": name})
    return RedirectResponse(f"/admin/partners/{partner.id}", status_code=302)


@require_auth
async def partner_detail(request: Request):
    templates = request.app.state.templates
    partner_id = request.path_params["id"]
    repo = PartnerRepo(request.app.state.db_pool)
    partner = await repo.get_by_id(UUID(str(partner_id)))
    if not partner:
        return templates.TemplateResponse(
            request, "partners/list.html",
            {"partners": [], "page_info": get_page_info(1, 0), "flash_error": "Partner not found"},
            status_code=404,
        )
    return templates.TemplateResponse(request, "partners/detail.html", {"partner": partner})


@require_role("super_admin", "admin")
async def partner_status(request: Request):
    partner_id = request.path_params["id"]
    form = await request.form()
    new_status = form.get("status", "active")

    repo = PartnerRepo(request.app.state.db_pool)
    await repo.update_status(UUID(str(partner_id)), new_status)
    await log_action(
        request, "partner.update_status", "partner",
        UUID(str(partner_id)), {"status": new_status},
    )
    return RedirectResponse(f"/admin/partners/{partner_id}", status_code=302)
