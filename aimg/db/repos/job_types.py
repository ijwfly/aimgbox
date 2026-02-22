from __future__ import annotations

from uuid import UUID

import asyncpg

from aimg.db.models import JobType, JobTypeProvider
from aimg.db.repos import BaseRepo


class JobTypeRepo(BaseRepo):
    async def get_by_slug(
        self, slug: str, *, conn: asyncpg.Connection | None = None
    ) -> JobType | None:
        row = await self._fetchrow(
            "SELECT * FROM job_types WHERE slug = $1", slug, conn=conn
        )
        return JobType(**dict(row)) if row else None

    async def get_by_id(
        self, jt_id: UUID, *, conn: asyncpg.Connection | None = None
    ) -> JobType | None:
        row = await self._fetchrow(
            "SELECT * FROM job_types WHERE id = $1", jt_id, conn=conn
        )
        return JobType(**dict(row)) if row else None

    async def upsert(
        self,
        slug: str,
        name: str,
        description: str | None,
        input_schema: dict,
        output_schema: dict,
        *,
        conn: asyncpg.Connection | None = None,
    ) -> JobType:
        row = await self._fetchrow(
            """INSERT INTO job_types (slug, name, description, input_schema, output_schema)
               VALUES ($1, $2, $3, $4, $5)
               ON CONFLICT (slug) DO UPDATE
               SET name = $2, description = $3, input_schema = $4,
                   output_schema = $5, updated_at = now()
               RETURNING *""",
            slug,
            name,
            description,
            input_schema,
            output_schema,
            conn=conn,
        )
        return JobType(**dict(row))

    async def list_active(
        self, *, conn: asyncpg.Connection | None = None
    ) -> list[JobType]:
        rows = await self._fetch(
            "SELECT * FROM job_types WHERE status = 'active' ORDER BY slug",
            conn=conn,
        )
        return [JobType(**dict(r)) for r in rows]

    async def get_providers_for_job_type(
        self, job_type_id: UUID, *, conn: asyncpg.Connection | None = None
    ) -> list[JobTypeProvider]:
        rows = await self._fetch(
            """SELECT * FROM job_type_providers
               WHERE job_type_id = $1
               ORDER BY priority""",
            job_type_id,
            conn=conn,
        )
        return [JobTypeProvider(**dict(r)) for r in rows]

    async def list_all_admin(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        conn: asyncpg.Connection | None = None,
    ) -> list[JobType]:
        rows = await self._fetch(
            "SELECT * FROM job_types ORDER BY slug LIMIT $1 OFFSET $2",
            limit,
            offset,
            conn=conn,
        )
        return [JobType(**dict(r)) for r in rows]

    async def count_all(self, *, conn: asyncpg.Connection | None = None) -> int:
        row = await self._fetchrow(
            "SELECT count(*) AS cnt FROM job_types", conn=conn
        )
        return row["cnt"]

    async def update(
        self,
        jt_id: UUID,
        *,
        credit_cost: int | None = None,
        timeout_seconds: int | None = None,
        status: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> JobType | None:
        sets: list[str] = []
        args: list = []
        idx = 2  # $1 = id

        if credit_cost is not None:
            sets.append(f"credit_cost = ${idx}")
            args.append(credit_cost)
            idx += 1

        if timeout_seconds is not None:
            sets.append(f"timeout_seconds = ${idx}")
            args.append(timeout_seconds)
            idx += 1

        if status is not None:
            sets.append(f"status = ${idx}")
            args.append(status)
            idx += 1

        if not sets:
            return await self.get_by_id(jt_id, conn=conn)

        sets.append("updated_at = now()")
        row = await self._fetchrow(
            f"UPDATE job_types SET {', '.join(sets)} WHERE id = $1 RETURNING *",
            jt_id,
            *args,
            conn=conn,
        )
        return JobType(**dict(row)) if row else None

    async def remove_provider(
        self,
        job_type_id: UUID,
        provider_id: UUID,
        *,
        conn: asyncpg.Connection | None = None,
    ) -> bool:
        result = await self._execute(
            "DELETE FROM job_type_providers WHERE job_type_id = $1 AND provider_id = $2",
            job_type_id,
            provider_id,
            conn=conn,
        )
        return result.endswith("1")

    async def add_provider(
        self,
        job_type_id: UUID,
        provider_id: UUID,
        *,
        priority: int = 0,
        config_override: dict | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> JobTypeProvider:
        row = await self._fetchrow(
            """INSERT INTO job_type_providers (job_type_id, provider_id, priority, config_override)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (job_type_id, provider_id) DO UPDATE
               SET priority = $3, config_override = $4
               RETURNING *""",
            job_type_id,
            provider_id,
            priority,
            config_override or {},
            conn=conn,
        )
        return JobTypeProvider(**dict(row))
