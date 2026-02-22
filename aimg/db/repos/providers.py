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

    async def list_all(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        conn: asyncpg.Connection | None = None,
    ) -> list[Provider]:
        rows = await self._fetch(
            "SELECT * FROM providers ORDER BY slug LIMIT $1 OFFSET $2",
            limit,
            offset,
            conn=conn,
        )
        return [Provider(**dict(r)) for r in rows]

    async def count(self, *, conn: asyncpg.Connection | None = None) -> int:
        row = await self._fetchrow(
            "SELECT count(*) AS cnt FROM providers", conn=conn
        )
        return row["cnt"]

    async def update(
        self,
        provider_id: UUID,
        *,
        name: str | None = None,
        adapter_class: str | None = None,
        base_url: str | None = None,
        api_key_encrypted: str | None = None,
        config: dict | None = None,
        status: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> Provider | None:
        sets: list[str] = []
        args: list = []
        idx = 2  # $1 = id

        if name is not None:
            sets.append(f"name = ${idx}")
            args.append(name)
            idx += 1

        if adapter_class is not None:
            sets.append(f"adapter_class = ${idx}")
            args.append(adapter_class)
            idx += 1

        if base_url is not None:
            sets.append(f"base_url = ${idx}")
            args.append(base_url)
            idx += 1

        if api_key_encrypted is not None:
            sets.append(f"api_key_encrypted = ${idx}")
            args.append(api_key_encrypted)
            idx += 1

        if config is not None:
            sets.append(f"config = ${idx}")
            args.append(config)
            idx += 1

        if status is not None:
            sets.append(f"status = ${idx}")
            args.append(status)
            idx += 1

        if not sets:
            return await self.get_by_id(provider_id, conn=conn)

        sets.append("updated_at = now()")
        row = await self._fetchrow(
            f"UPDATE providers SET {', '.join(sets)} WHERE id = $1 RETURNING *",
            provider_id,
            *args,
            conn=conn,
        )
        return Provider(**dict(row)) if row else None
