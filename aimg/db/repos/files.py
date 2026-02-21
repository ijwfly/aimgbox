from __future__ import annotations

from uuid import UUID

import asyncpg

from aimg.db.models import File
from aimg.db.repos import BaseRepo


class FileRepo(BaseRepo):
    async def create(
        self,
        integration_id: UUID,
        user_id: UUID | None,
        s3_bucket: str,
        s3_key: str,
        content_type: str,
        size_bytes: int,
        purpose: str,
        *,
        original_filename: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> File:
        row = await self._fetchrow(
            """INSERT INTO files
               (integration_id, user_id, s3_bucket, s3_key,
                original_filename, content_type, size_bytes, purpose)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING *""",
            integration_id,
            user_id,
            s3_bucket,
            s3_key,
            original_filename,
            content_type,
            size_bytes,
            purpose,
            conn=conn,
        )
        return File(**dict(row))

    async def get_by_id(
        self, file_id: UUID, *, conn: asyncpg.Connection | None = None
    ) -> File | None:
        row = await self._fetchrow(
            "SELECT * FROM files WHERE id = $1", file_id, conn=conn
        )
        return File(**dict(row)) if row else None
