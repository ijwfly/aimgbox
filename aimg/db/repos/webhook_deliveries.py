from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

from aimg.db.models import WebhookDelivery
from aimg.db.repos import BaseRepo


class WebhookDeliveryRepo(BaseRepo):
    async def create(
        self,
        integration_id: UUID,
        job_id: UUID,
        event: str,
        payload: dict,
        *,
        next_retry_at: datetime | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> WebhookDelivery:
        row = await self._fetchrow(
            """INSERT INTO webhook_deliveries
               (integration_id, job_id, event, payload, next_retry_at)
               VALUES ($1, $2, $3, $4, $5) RETURNING *""",
            integration_id,
            job_id,
            event,
            payload,
            next_retry_at,
            conn=conn,
        )
        return WebhookDelivery(**dict(row))

    async def get_pending_retries(
        self, now: datetime, *, limit: int = 50, conn: asyncpg.Connection | None = None
    ) -> list[WebhookDelivery]:
        rows = await self._fetch(
            """SELECT * FROM webhook_deliveries
               WHERE status = 'pending' AND next_retry_at <= $1
               ORDER BY next_retry_at
               LIMIT $2""",
            now,
            limit,
            conn=conn,
        )
        return [WebhookDelivery(**dict(r)) for r in rows]

    async def update_delivery(
        self,
        delivery_id: UUID,
        *,
        status: str,
        attempts: int,
        last_status_code: int | None = None,
        last_error: str | None = None,
        next_retry_at: datetime | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> WebhookDelivery | None:
        row = await self._fetchrow(
            """UPDATE webhook_deliveries
               SET status = $2, attempts = $3, last_status_code = $4,
                   last_error = $5, next_retry_at = $6, updated_at = now()
               WHERE id = $1 RETURNING *""",
            delivery_id,
            status,
            attempts,
            last_status_code,
            last_error,
            next_retry_at,
            conn=conn,
        )
        return WebhookDelivery(**dict(row)) if row else None
