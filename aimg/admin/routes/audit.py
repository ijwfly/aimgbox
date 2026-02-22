from __future__ import annotations

from starlette.requests import Request

from aimg.admin.decorators import require_auth
from aimg.admin.pagination import get_page_info
from aimg.db.repos.audit_log import AuditLogRepo


@require_auth
async def audit_list(request: Request):
    templates = request.app.state.templates
    db_pool = request.app.state.db_pool
    repo = AuditLogRepo(db_pool)

    page = int(request.query_params.get("page", 1))
    entity_type = request.query_params.get("entity_type") or None
    action_prefix = request.query_params.get("action_prefix") or None

    total = await repo.count(entity_type=entity_type, action_prefix=action_prefix)
    page_info = get_page_info(page, total)
    entries = await repo.list_entries(
        limit=page_info["per_page"],
        offset=page_info["offset"],
        entity_type=entity_type,
        action_prefix=action_prefix,
    )

    ctx = {
        "entries": entries,
        "page_info": page_info,
        "filter_entity_type": entity_type or "",
        "filter_action_prefix": action_prefix or "",
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "audit/_rows.html", ctx)
    return templates.TemplateResponse(request, "audit/list.html", ctx)
