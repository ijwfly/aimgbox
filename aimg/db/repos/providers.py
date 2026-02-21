from __future__ import annotations

from uuid import UUID

import asyncpg

from aimg.db.models import Provider
from aimg.db.repos import BaseRepo


class ProviderRepo(BaseRepo):
    async def get_by_id(
        self, provider_id: UUID, *, conn: asyncpg.Connection | None = None
    ) -> Provider | None:
        row = await self._fetchrow(
            "SELECT * FROM providers WHERE id = $1", provider_id, conn=conn
        )
        return Provider(**dict(row)) if row else None

    async def get_by_slug(
        self, slug: str, *, conn: asyncpg.Connection | None = None
    ) -> Provider | None:
        row = await self._fetchrow(
            "SELECT * FROM providers WHERE slug = $1", slug, conn=conn
        )
        return Provider(**dict(row)) if row else None

    async def create(
        self,
        slug: str,
        name: str,
        adapter_class: str,
        api_key_encrypted: str,
        *,
        base_url: str | None = None,
        config: dict | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> Provider:
        row = await self._fetchrow(
            """INSERT INTO providers (slug, name, adapter_class, api_key_encrypted,
                                     base_url, config)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
            slug,
            name,
            adapter_class,
            api_key_encrypted,
            base_url,
            config or {},
            conn=conn,
        )
        return Provider(**dict(row))
