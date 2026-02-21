from __future__ import annotations

from uuid import UUID

import asyncpg

from aimg.db.models import ApiKey
from aimg.db.repos import BaseRepo


class ApiKeyRepo(BaseRepo):
    async def create(
        self,
        integration_id: UUID,
        key_hash: str,
        *,
        label: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> ApiKey:
        row = await self._fetchrow(
            """INSERT INTO api_keys (integration_id, key_hash, label)
               VALUES ($1, $2, $3) RETURNING *""",
            integration_id,
            key_hash,
            label,
            conn=conn,
        )
        return ApiKey(**dict(row))

    async def get_by_id(
        self, key_id: UUID, *, conn: asyncpg.Connection | None = None
    ) -> ApiKey | None:
        row = await self._fetchrow(
            "SELECT * FROM api_keys WHERE id = $1", key_id, conn=conn
        )
        return ApiKey(**dict(row)) if row else None

    async def get_by_hash(
        self, key_hash: str, *, conn: asyncpg.Connection | None = None
    ) -> ApiKey | None:
        row = await self._fetchrow(
            "SELECT * FROM api_keys WHERE key_hash = $1", key_hash, conn=conn
        )
        return ApiKey(**dict(row)) if row else None
