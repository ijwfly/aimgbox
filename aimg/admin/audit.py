from __future__ import annotations

from uuid import UUID

from starlette.requests import Request

from aimg.db.repos.audit_log import AuditLogRepo


async def log_action(
    request: Request,
    action: str,
    entity_type: str,
    entity_id: UUID | None = None,
    details: dict | None = None,
) -> None:
    admin_user = request.state.admin_user
    admin_user_id = UUID(admin_user["id"]) if admin_user else None
    ip_address = request.client.host if request.client else None

    repo = AuditLogRepo(request.app.state.db_pool)
    await repo.create(
        admin_user_id=admin_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=ip_address,
    )
