from __future__ import annotations

from uuid import UUID

import asyncpg

from aimg.db.models import AuditLogEntry
from aimg.db.repos import BaseRepo


class AuditLogRepo(BaseRepo):
    async def create(
        self,
        admin_user_id: UUID | None,
        action: str,
        entity_type: str,
        entity_id: UUID | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
        *,
        conn: asyncpg.Connection | None = None,
    ) -> AuditLogEntry:
        row = await self._fetchrow(
            """INSERT INTO audit_log
               (admin_user_id, action, entity_type, entity_id, details, ip_address)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
            admin_user_id,
            action,
            entity_type,
            entity_id,
            details or {},
            ip_address,
            conn=conn,
        )
        return self._to_entry(row)

    @staticmethod
    def _to_entry(row) -> AuditLogEntry:
        data = dict(row)
        if data.get("ip_address") is not None:
            data["ip_address"] = str(data["ip_address"])
        return AuditLogEntry(**data)

    async def list_entries(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        entity_type: str | None = None,
        admin_user_id: UUID | None = None,
        action_prefix: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> list[AuditLogEntry]:
        conditions: list[str] = []
        args: list = []
        idx = 1

        if entity_type:
            conditions.append(f"entity_type = ${idx}")
            args.append(entity_type)
            idx += 1

        if admin_user_id:
            conditions.append(f"admin_user_id = ${idx}")
            args.append(admin_user_id)
            idx += 1

        if action_prefix:
            conditions.append(f"action LIKE ${idx}")
            args.append(f"{action_prefix}%")
            idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        args.extend([limit, offset])

        rows = await self._fetch(
            f"""SELECT * FROM audit_log {where}
                ORDER BY created_at DESC
                LIMIT ${idx} OFFSET ${idx + 1}""",
            *args,
            conn=conn,
        )
        return [self._to_entry(r) for r in rows]

    async def count(
        self,
        *,
        entity_type: str | None = None,
        admin_user_id: UUID | None = None,
        action_prefix: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> int:
        conditions: list[str] = []
        args: list = []
        idx = 1

        if entity_type:
            conditions.append(f"entity_type = ${idx}")
            args.append(entity_type)
            idx += 1

        if admin_user_id:
            conditions.append(f"admin_user_id = ${idx}")
            args.append(admin_user_id)
            idx += 1

        if action_prefix:
            conditions.append(f"action LIKE ${idx}")
            args.append(f"{action_prefix}%")
            idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        row = await self._fetchrow(
            f"SELECT count(*) AS cnt FROM audit_log {where}",
            *args,
            conn=conn,
        )
        return row["cnt"]
