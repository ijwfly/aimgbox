from __future__ import annotations

from uuid import UUID

import asyncpg

from aimg.db.models import Integration
from aimg.db.repos import BaseRepo


class IntegrationRepo(BaseRepo):
    async def get_by_id(
        self, integration_id: UUID, *, conn: asyncpg.Connection | None = None
    ) -> Integration | None:
        row = await self._fetchrow(
            "SELECT * FROM integrations WHERE id = $1", integration_id, conn=conn
        )
        return Integration(**dict(row)) if row else None

    async def create(
        self,
        partner_id: UUID,
        name: str,
        *,
        default_free_credits: int = 10,
        webhook_url: str | None = None,
        webhook_secret: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> Integration:
        row = await self._fetchrow(
            """INSERT INTO integrations
               (partner_id, name, default_free_credits, webhook_url, webhook_secret)
               VALUES ($1, $2, $3, $4, $5) RETURNING *""",
            partner_id,
            name,
            default_free_credits,
            webhook_url,
            webhook_secret,
            conn=conn,
        )
        return Integration(**dict(row))

    async def list_all(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        partner_id: UUID | None = None,
        status: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> list[Integration]:
        conditions: list[str] = []
        args: list = []
        idx = 1

        if partner_id:
            conditions.append(f"partner_id = ${idx}")
            args.append(partner_id)
            idx += 1

        if status:
            conditions.append(f"status = ${idx}")
            args.append(status)
            idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        args.extend([limit, offset])

        rows = await self._fetch(
            f"""SELECT * FROM integrations {where}
                ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}""",
            *args,
            conn=conn,
        )
        return [Integration(**dict(r)) for r in rows]

    async def count(
        self,
        *,
        partner_id: UUID | None = None,
        status: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> int:
        conditions: list[str] = []
        args: list = []
        idx = 1

        if partner_id:
            conditions.append(f"partner_id = ${idx}")
            args.append(partner_id)
            idx += 1

        if status:
            conditions.append(f"status = ${idx}")
            args.append(status)
            idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        row = await self._fetchrow(
            f"SELECT count(*) AS cnt FROM integrations {where}",
            *args,
            conn=conn,
        )
        return row["cnt"]

    async def list_by_partner(
        self, partner_id: UUID, *, conn: asyncpg.Connection | None = None
    ) -> list[Integration]:
        rows = await self._fetch(
            "SELECT * FROM integrations WHERE partner_id = $1 ORDER BY created_at DESC",
            partner_id,
            conn=conn,
        )
        return [Integration(**dict(r)) for r in rows]

    async def update_status(
        self, integration_id: UUID, status: str, *, conn: asyncpg.Connection | None = None
    ) -> Integration | None:
        row = await self._fetchrow(
            """UPDATE integrations SET status = $2, updated_at = now()
               WHERE id = $1 RETURNING *""",
            integration_id,
            status,
            conn=conn,
        )
        return Integration(**dict(row)) if row else None

    async def update(
        self,
        integration_id: UUID,
        *,
        name: str | None = None,
        webhook_url: str | None = None,
        webhook_secret: str | None = None,
        rate_limit_rpm: int | None = None,
        default_free_credits: int | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> Integration | None:
        sets: list[str] = []
        args: list = []
        idx = 2  # $1 is id

        if name is not None:
            sets.append(f"name = ${idx}")
            args.append(name)
            idx += 1

        if webhook_url is not None:
            sets.append(f"webhook_url = ${idx}")
            args.append(webhook_url)
            idx += 1

        if webhook_secret is not None:
            sets.append(f"webhook_secret = ${idx}")
            args.append(webhook_secret)
            idx += 1

        if rate_limit_rpm is not None:
            sets.append(f"rate_limit_rpm = ${idx}")
            args.append(rate_limit_rpm)
            idx += 1

        if default_free_credits is not None:
            sets.append(f"default_free_credits = ${idx}")
            args.append(default_free_credits)
            idx += 1

        if not sets:
            return await self.get_by_id(integration_id, conn=conn)

        sets.append("updated_at = now()")
        row = await self._fetchrow(
            f"UPDATE integrations SET {', '.join(sets)} WHERE id = $1 RETURNING *",
            integration_id,
            *args,
            conn=conn,
        )
        return Integration(**dict(row)) if row else None
