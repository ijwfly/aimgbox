from __future__ import annotations

from uuid import UUID

import asyncpg

from aimg.db.models import User
from aimg.db.repos import BaseRepo


class UserRepo(BaseRepo):
    async def get_by_id(
        self, user_id: UUID, *, conn: asyncpg.Connection | None = None
    ) -> User | None:
        row = await self._fetchrow(
            "SELECT * FROM users WHERE id = $1", user_id, conn=conn
        )
        return User(**dict(row)) if row else None

    async def get_or_create(
        self,
        integration_id: UUID,
        external_user_id: str,
        *,
        default_free_credits: int = 0,
        conn: asyncpg.Connection | None = None,
    ) -> User:
        row = await self._fetchrow(
            "SELECT * FROM users WHERE integration_id = $1 AND external_user_id = $2",
            integration_id,
            external_user_id,
            conn=conn,
        )
        if row:
            return User(**dict(row))
        row = await self._fetchrow(
            """INSERT INTO users (integration_id, external_user_id, free_credits)
               VALUES ($1, $2, $3)
               ON CONFLICT (integration_id, external_user_id)
               DO UPDATE SET integration_id = users.integration_id
               RETURNING *""",
            integration_id,
            external_user_id,
            default_free_credits,
            conn=conn,
        )
        return User(**dict(row))

    async def update_credits(
        self,
        user_id: UUID,
        free_credits_delta: int,
        paid_credits_delta: int,
        *,
        conn: asyncpg.Connection | None = None,
    ) -> bool:
        result = await self._execute(
            """UPDATE users
               SET free_credits = free_credits + $2,
                   paid_credits = paid_credits + $3,
                   updated_at = now()
               WHERE id = $1
                 AND free_credits + $2 >= 0
                 AND paid_credits + $3 >= 0""",
            user_id,
            free_credits_delta,
            paid_credits_delta,
            conn=conn,
        )
        return result.endswith("1")

    async def force_set_credits(
        self,
        user_id: UUID,
        free_credits: int,
        paid_credits: int,
        *,
        conn: asyncpg.Connection | None = None,
    ) -> bool:
        result = await self._execute(
            """UPDATE users
               SET free_credits = $2, paid_credits = $3, updated_at = now()
               WHERE id = $1""",
            user_id,
            free_credits,
            paid_credits,
            conn=conn,
        )
        return result.endswith("1")

    async def list_all(
        self, *, conn: asyncpg.Connection | None = None
    ) -> list[User]:
        rows = await self._fetch("SELECT * FROM users", conn=conn)
        return [User(**dict(r)) for r in rows]
