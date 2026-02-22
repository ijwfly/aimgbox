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
