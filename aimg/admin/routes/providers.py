from __future__ import annotations

from uuid import UUID

from starlette.requests import Request
from starlette.responses import RedirectResponse

from aimg.admin.audit import log_action
from aimg.admin.decorators import require_role
from aimg.admin.pagination import get_page_info
from aimg.common.encryption import encrypt_value
from aimg.db.repos.providers import ProviderRepo


@require_role("super_admin", "admin")
async def provider_list(request: Request):
    templates = request.app.state.templates
    db_pool = request.app.state.db_pool
    repo = ProviderRepo(db_pool)

    page = int(request.query_params.get("page", 1))
    total = await repo.count()
    page_info = get_page_info(page, total)
    providers = await repo.list_all(
        limit=page_info["per_page"], offset=page_info["offset"],
    )

    ctx = {"providers": providers, "page_info": page_info}

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "providers/_rows.html", ctx)
    return templates.TemplateResponse(request, "providers/list.html", ctx)


@require_role("super_admin")
async def provider_new(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "providers/form.html")


@require_role("super_admin")
async def provider_create(request: Request):
    templates = request.app.state.templates
    settings = request.app.state.settings
    form = await request.form()

    slug = form.get("slug", "").strip()
    name = form.get("name", "").strip()
    adapter_class = form.get("adapter_class", "").strip()
    api_key = form.get("api_key", "").strip()
    base_url = form.get("base_url", "").strip() or None

    if not slug or not name or not adapter_class:
        return templates.TemplateResponse(
            request, "providers/form.html",
            {"error": "Slug, name, and adapter class are required"},
            status_code=400,
        )

    api_key_encrypted = (
        encrypt_value(api_key, settings.encryption_key) if api_key else "not-needed"
    )

    repo = ProviderRepo(request.app.state.db_pool)
    provider = await repo.create(
        slug=slug,
        name=name,
        adapter_class=adapter_class,
        api_key_encrypted=api_key_encrypted,
        base_url=base_url,
    )
    await log_action(
        request, "provider.create", "provider", provider.id,
        {"slug": slug, "name": name},
    )
    return RedirectResponse(f"/admin/providers/{provider.id}", status_code=302)


@require_role("super_admin", "admin")
async def provider_detail(request: Request):
    templates = request.app.state.templates
    provider_id = UUID(str(request.path_params["id"]))

    repo = ProviderRepo(request.app.state.db_pool)
    provider = await repo.get_by_id(provider_id)
    if not provider:
        return RedirectResponse("/admin/providers", status_code=302)

    return templates.TemplateResponse(request, "providers/detail.html", {
        "provider": provider,
    })


@require_role("super_admin")
async def provider_update(request: Request):
    settings = request.app.state.settings
    provider_id = UUID(str(request.path_params["id"]))
    form = await request.form()

    kwargs = {}
    if form.get("name"):
        kwargs["name"] = form["name"].strip()
    if form.get("adapter_class"):
        kwargs["adapter_class"] = form["adapter_class"].strip()
    if form.get("base_url") is not None:
        kwargs["base_url"] = form["base_url"].strip() or None
    if form.get("api_key"):
        kwargs["api_key_encrypted"] = encrypt_value(
            form["api_key"].strip(), settings.encryption_key
        )
    if form.get("status"):
        kwargs["status"] = form["status"]

    repo = ProviderRepo(request.app.state.db_pool)
    await repo.update(provider_id, **kwargs)

    log_details = {k: v for k, v in kwargs.items() if k != "api_key_encrypted"}
    if "api_key_encrypted" in kwargs:
        log_details["api_key"] = "***updated***"
    await log_action(
        request, "provider.update", "provider", provider_id, log_details,
    )
    return RedirectResponse(f"/admin/providers/{provider_id}", status_code=302)
