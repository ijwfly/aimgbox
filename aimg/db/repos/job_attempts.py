from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

from aimg.db.models import JobAttempt
from aimg.db.repos import BaseRepo


class JobAttemptRepo(BaseRepo):
    async def create(
        self,
        job_id: UUID,
        provider_id: UUID,
        attempt_number: int,
        status: str,
        started_at: datetime,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        duration_ms: int | None = None,
        completed_at: datetime | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> JobAttempt:
        row = await self._fetchrow(
            """INSERT INTO job_attempts
               (job_id, provider_id, attempt_number, status, started_at,
                error_code, error_message, duration_ms, completed_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING *""",
            job_id,
            provider_id,
            attempt_number,
            status,
            started_at,
            error_code,
            error_message,
            duration_ms,
            completed_at,
            conn=conn,
        )
        return JobAttempt(**dict(row))

    async def list_by_job(
        self, job_id: UUID, *, conn: asyncpg.Connection | None = None
    ) -> list[JobAttempt]:
        rows = await self._fetch(
            "SELECT * FROM job_attempts WHERE job_id = $1 ORDER BY attempt_number",
            job_id,
            conn=conn,
        )
        return [JobAttempt(**dict(r)) for r in rows]
