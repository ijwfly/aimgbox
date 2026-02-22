from __future__ import annotations

from uuid import UUID

from starlette.requests import Request
from starlette.responses import RedirectResponse

from aimg.admin.audit import log_action
from aimg.admin.decorators import require_auth, require_role
from aimg.admin.pagination import get_page_info
from aimg.db.repos.api_keys import ApiKeyRepo
from aimg.db.repos.integrations import IntegrationRepo
from aimg.db.repos.partners import PartnerRepo


@require_auth
async def integration_list(request: Request):
    templates = request.app.state.templates
    db_pool = request.app.state.db_pool
    repo = IntegrationRepo(db_pool)

    page = int(request.query_params.get("page", 1))
    partner_id_str = request.query_params.get("partner_id")
    partner_id = UUID(partner_id_str) if partner_id_str else None
    status = request.query_params.get("status")

    total = await repo.count(partner_id=partner_id, status=status)
    page_info = get_page_info(page, total)
    integrations = await repo.list_all(
        limit=page_info["per_page"], offset=page_info["offset"],
        partner_id=partner_id, status=status,
    )

    ctx = {
        "integrations": integrations,
        "page_info": page_info,
        "filter_partner_id": partner_id_str or "",
        "filter_status": status or "",
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "integrations/_rows.html", ctx)
    return templates.TemplateResponse(request, "integrations/list.html", ctx)


@require_role("super_admin", "admin")
async def integration_new(request: Request):
    templates = request.app.state.templates
    partners = await PartnerRepo(request.app.state.db_pool).list_all(limit=1000)
    return templates.TemplateResponse(request, "integrations/form.html", {"partners": partners})


@require_role("super_admin", "admin")
async def integration_create(request: Request):
    templates = request.app.state.templates
    form = await request.form()
    name = form.get("name", "").strip()
    partner_id_str = form.get("partner_id", "")
    default_free_credits = int(form.get("default_free_credits", 10))
    webhook_url = form.get("webhook_url", "").strip() or None
    webhook_secret = form.get("webhook_secret", "").strip() or None

    if not name or not partner_id_str:
        partners = await PartnerRepo(request.app.state.db_pool).list_all(limit=1000)
        return templates.TemplateResponse(
            request, "integrations/form.html",
            {"partners": partners, "error": "Name and partner are required"},
            status_code=400,
        )

    repo = IntegrationRepo(request.app.state.db_pool)
    integration = await repo.create(
        UUID(partner_id_str), name,
        default_free_credits=default_free_credits,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
    )
    await log_action(
        request, "integration.create", "integration", integration.id,
        {"name": name, "partner_id": partner_id_str},
    )
    return RedirectResponse(f"/admin/integrations/{integration.id}", status_code=302)


@require_auth
async def integration_detail(request: Request):
    templates = request.app.state.templates
    db_pool = request.app.state.db_pool
    integration_id = UUID(str(request.path_params["id"]))

    repo = IntegrationRepo(db_pool)
    integration = await repo.get_by_id(integration_id)
    if not integration:
        return templates.TemplateResponse(
            request, "integrations/list.html",
            {"integrations": [], "page_info": get_page_info(1, 0),
             "flash_error": "Integration not found"},
            status_code=404,
        )

    partner = await PartnerRepo(db_pool).get_by_id(integration.partner_id)
    keys = await ApiKeyRepo(db_pool).list_by_integration(integration_id)

    return templates.TemplateResponse(request, "integrations/detail.html", {
        "integration": integration,
        "partner": partner,
        "keys": keys,
    })


@require_role("super_admin", "admin")
async def integration_update(request: Request):
    integration_id = UUID(str(request.path_params["id"]))
    form = await request.form()

    kwargs = {}
    if form.get("name"):
        kwargs["name"] = form["name"].strip()
    if form.get("webhook_url") is not None:
        kwargs["webhook_url"] = form["webhook_url"].strip() or None
    if form.get("webhook_secret") is not None:
        kwargs["webhook_secret"] = form["webhook_secret"].strip() or None
    if form.get("rate_limit_rpm"):
        kwargs["rate_limit_rpm"] = int(form["rate_limit_rpm"])
    if form.get("default_free_credits"):
        kwargs["default_free_credits"] = int(form["default_free_credits"])

    repo = IntegrationRepo(request.app.state.db_pool)
    await repo.update(integration_id, **kwargs)
    await log_action(
        request, "integration.update", "integration", integration_id, kwargs,
    )
    return RedirectResponse(f"/admin/integrations/{integration_id}", status_code=302)


@require_role("super_admin", "admin")
async def integration_status(request: Request):
    integration_id = UUID(str(request.path_params["id"]))
    form = await request.form()
    new_status = form.get("status", "active")

    repo = IntegrationRepo(request.app.state.db_pool)
    await repo.update_status(integration_id, new_status)
    await log_action(
        request, "integration.update_status", "integration",
        integration_id, {"status": new_status},
    )
    return RedirectResponse(f"/admin/integrations/{integration_id}", status_code=302)
