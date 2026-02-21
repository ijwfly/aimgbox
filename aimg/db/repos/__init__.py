from __future__ import annotations

from typing import Any

import asyncpg


class BaseRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def _fetchrow(
        self, query: str, *args: Any, conn: asyncpg.Connection | None = None
    ) -> asyncpg.Record | None:
        if conn:
            return await conn.fetchrow(query, *args)
        async with self._pool.acquire() as c:
            return await c.fetchrow(query, *args)

    async def _fetch(
        self, query: str, *args: Any, conn: asyncpg.Connection | None = None
    ) -> list[asyncpg.Record]:
        if conn:
            return await conn.fetch(query, *args)
        async with self._pool.acquire() as c:
            return await c.fetch(query, *args)

    async def _execute(
        self, query: str, *args: Any, conn: asyncpg.Connection | None = None
    ) -> str:
        if conn:
            return await conn.execute(query, *args)
        async with self._pool.acquire() as c:
            return await c.execute(query, *args)
