from __future__ import annotations

from uuid import UUID

import asyncpg

from aimg.db.models import Job
from aimg.db.repos import BaseRepo


class JobRepo(BaseRepo):
    async def create(
        self,
        integration_id: UUID,
        user_id: UUID,
        job_type_id: UUID,
        input_data: dict,
        credit_charged: int,
        *,
        language: str = "en",
        idempotency_key: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> Job:
        row = await self._fetchrow(
            """INSERT INTO jobs
               (integration_id, user_id, job_type_id, input_data,
                credit_charged, language, idempotency_key)
               VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *""",
            integration_id,
            user_id,
            job_type_id,
            input_data,
            credit_charged,
            language,
            idempotency_key,
            conn=conn,
        )
        return Job(**dict(row))

    async def get_by_id(
        self, job_id: UUID, *, conn: asyncpg.Connection | None = None
    ) -> Job | None:
        row = await self._fetchrow(
            "SELECT * FROM jobs WHERE id = $1", job_id, conn=conn
        )
        return Job(**dict(row)) if row else None

    async def update_status(
        self,
        job_id: UUID,
        status: str,
        *,
        provider_id: UUID | None = None,
        output_data: dict | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> Job | None:
        if status == "running":
            row = await self._fetchrow(
                """UPDATE jobs
                   SET status = $2, started_at = now(), provider_id = $3,
                       attempts = attempts + 1, updated_at = now()
                   WHERE id = $1 RETURNING *""",
                job_id,
                status,
                provider_id,
                conn=conn,
            )
        elif status == "succeeded":
            row = await self._fetchrow(
                """UPDATE jobs
                   SET status = $2, output_data = $3, provider_id = $4,
                       completed_at = now(), updated_at = now()
                   WHERE id = $1 RETURNING *""",
                job_id,
                status,
                output_data,
                provider_id,
                conn=conn,
            )
        elif status == "failed":
            row = await self._fetchrow(
                """UPDATE jobs
                   SET status = $2, error_code = $3, error_message = $4,
                       completed_at = now(), updated_at = now()
                   WHERE id = $1 RETURNING *""",
                job_id,
                status,
                error_code,
                error_message,
                conn=conn,
            )
        else:
            row = await self._fetchrow(
                """UPDATE jobs SET status = $2, updated_at = now()
                   WHERE id = $1 RETURNING *""",
                job_id,
                status,
                conn=conn,
            )
        return Job(**dict(row)) if row else None

    async def increment_attempts(
        self,
        job_id: UUID,
        provider_id: UUID,
        *,
        conn: asyncpg.Connection | None = None,
    ) -> None:
        await self._execute(
            """UPDATE jobs
               SET attempts = attempts + 1, provider_id = $2, updated_at = now()
               WHERE id = $1""",
            job_id,
            provider_id,
            conn=conn,
        )
