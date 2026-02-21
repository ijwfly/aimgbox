from __future__ import annotations

from uuid import UUID

import asyncpg

from aimg.db.models import Partner
from aimg.db.repos import BaseRepo


class PartnerRepo(BaseRepo):
    async def get_by_id(
        self, partner_id: UUID, *, conn: asyncpg.Connection | None = None
    ) -> Partner | None:
        row = await self._fetchrow(
            "SELECT * FROM partners WHERE id = $1", partner_id, conn=conn
        )
        return Partner(**dict(row)) if row else None

    async def create(
        self, name: str, *, conn: asyncpg.Connection | None = None
    ) -> Partner:
        row = await self._fetchrow(
            "INSERT INTO partners (name) VALUES ($1) RETURNING *",
            name,
            conn=conn,
        )
        return Partner(**dict(row))
