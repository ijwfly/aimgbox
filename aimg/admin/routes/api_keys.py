from __future__ import annotations

from uuid import UUID

from starlette.requests import Request
from starlette.responses import RedirectResponse

from aimg.admin.audit import log_action
from aimg.admin.decorators import require_role
from aimg.db.repos.api_keys import ApiKeyRepo
from aimg.db.repos.integrations import IntegrationRepo
from aimg.services.auth import generate_api_key, hash_api_key


@require_role("super_admin", "admin")
async def generate_key(request: Request):
    templates = request.app.state.templates
    db_pool = request.app.state.db_pool
    settings = request.app.state.settings
    integration_id = UUID(str(request.path_params["id"]))

    integration_repo = IntegrationRepo(db_pool)
    integration = await integration_repo.get_by_id(integration_id)
    if not integration:
        return RedirectResponse("/admin/integrations", status_code=302)

    form = await request.form()
    label = form.get("label", "").strip() or None

    token = generate_api_key(
        integration_id=integration.id,
        partner_id=integration.partner_id,
        key_id=integration.id,
        secret=settings.jwt_secret,
    )
    key_hash = hash_api_key(token)

    api_key_repo = ApiKeyRepo(db_pool)
    api_key = await api_key_repo.create(
        integration_id=integration.id,
        key_hash=key_hash,
        label=label,
    )

    await log_action(
        request, "api_key.generate", "api_key", api_key.id,
        {"integration_id": str(integration_id), "label": label},
    )

    keys = await api_key_repo.list_by_integration(integration_id)
    return templates.TemplateResponse(request, "api_keys/_generated.html", {
        "token": token,
        "api_key": api_key,
        "keys": keys,
        "integration": integration,
    })


@require_role("super_admin", "admin")
async def revoke_key(request: Request):
    db_pool = request.app.state.db_pool
    key_id = UUID(str(request.path_params["id"]))

    api_key_repo = ApiKeyRepo(db_pool)
    api_key = await api_key_repo.get_by_id(key_id)
    if not api_key:
        return RedirectResponse("/admin/integrations", status_code=302)

    await api_key_repo.revoke(key_id)

    # Add to Redis revoked set
    redis_client = request.app.state.redis
    await redis_client.sadd("aimg:revoked_keys", api_key.key_hash)

    await log_action(
        request, "api_key.revoke", "api_key", key_id,
        {"integration_id": str(api_key.integration_id)},
    )

    return RedirectResponse(
        f"/admin/integrations/{api_key.integration_id}", status_code=302
    )
