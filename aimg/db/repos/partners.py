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

    async def list_all(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> list[Partner]:
        if status:
            rows = await self._fetch(
                """SELECT * FROM partners WHERE status = $1
                   ORDER BY created_at DESC LIMIT $2 OFFSET $3""",
                status,
                limit,
                offset,
                conn=conn,
            )
        else:
            rows = await self._fetch(
                "SELECT * FROM partners ORDER BY created_at DESC LIMIT $1 OFFSET $2",
                limit,
                offset,
                conn=conn,
            )
        return [Partner(**dict(r)) for r in rows]

    async def count(
        self, *, status: str | None = None, conn: asyncpg.Connection | None = None
    ) -> int:
        if status:
            row = await self._fetchrow(
                "SELECT count(*) AS cnt FROM partners WHERE status = $1",
                status,
                conn=conn,
            )
        else:
            row = await self._fetchrow(
                "SELECT count(*) AS cnt FROM partners", conn=conn
            )
        return row["cnt"]

    async def update_status(
        self, partner_id: UUID, status: str, *, conn: asyncpg.Connection | None = None
    ) -> Partner | None:
        row = await self._fetchrow(
            """UPDATE partners SET status = $2, updated_at = now()
               WHERE id = $1 RETURNING *""",
            partner_id,
            status,
            conn=conn,
        )
        return Partner(**dict(row)) if row else None

    async def update_name(
        self, partner_id: UUID, name: str, *, conn: asyncpg.Connection | None = None
    ) -> Partner | None:
        row = await self._fetchrow(
            """UPDATE partners SET name = $2, updated_at = now()
               WHERE id = $1 RETURNING *""",
            partner_id,
            name,
            conn=conn,
        )
        return Partner(**dict(row)) if row else None
