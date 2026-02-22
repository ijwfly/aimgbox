from __future__ import annotations

from uuid import UUID

import asyncpg

from aimg.db.models import AdminUser
from aimg.db.repos import BaseRepo


class AdminUserRepo(BaseRepo):
    async def get_by_id(
        self, user_id: UUID, *, conn: asyncpg.Connection | None = None
    ) -> AdminUser | None:
        row = await self._fetchrow(
            "SELECT * FROM admin_users WHERE id = $1", user_id, conn=conn
        )
        return AdminUser(**dict(row)) if row else None

    async def get_by_username(
        self, username: str, *, conn: asyncpg.Connection | None = None
    ) -> AdminUser | None:
        row = await self._fetchrow(
            "SELECT * FROM admin_users WHERE username = $1", username, conn=conn
        )
        return AdminUser(**dict(row)) if row else None

    async def create(
        self,
        username: str,
        password_hash: str,
        role: str = "viewer",
        *,
        conn: asyncpg.Connection | None = None,
    ) -> AdminUser:
        row = await self._fetchrow(
            """INSERT INTO admin_users (username, password_hash, role)
               VALUES ($1, $2, $3) RETURNING *""",
            username,
            password_hash,
            role,
            conn=conn,
        )
        return AdminUser(**dict(row))

    async def update_status(
        self, user_id: UUID, status: str, *, conn: asyncpg.Connection | None = None
    ) -> AdminUser | None:
        row = await self._fetchrow(
            """UPDATE admin_users SET status = $2, updated_at = now()
               WHERE id = $1 RETURNING *""",
            user_id,
            status,
            conn=conn,
        )
        return AdminUser(**dict(row)) if row else None

    async def update_password(
        self, user_id: UUID, password_hash: str, *, conn: asyncpg.Connection | None = None
    ) -> AdminUser | None:
        row = await self._fetchrow(
            """UPDATE admin_users SET password_hash = $2, updated_at = now()
               WHERE id = $1 RETURNING *""",
            user_id,
            password_hash,
            conn=conn,
        )
        return AdminUser(**dict(row)) if row else None

    async def list_all(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        conn: asyncpg.Connection | None = None,
    ) -> list[AdminUser]:
        rows = await self._fetch(
            "SELECT * FROM admin_users ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit,
            offset,
            conn=conn,
        )
        return [AdminUser(**dict(r)) for r in rows]

    async def count(self, *, conn: asyncpg.Connection | None = None) -> int:
        row = await self._fetchrow(
            "SELECT count(*) AS cnt FROM admin_users", conn=conn
        )
        return row["cnt"]
