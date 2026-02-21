from __future__ import annotations

from uuid import UUID

import asyncpg

from aimg.db.models import CreditTransaction
from aimg.db.repos import BaseRepo


class CreditTransactionRepo(BaseRepo):
    async def create(
        self,
        user_id: UUID,
        amount: int,
        credit_type: str,
        reason: str,
        balance_after: int,
        *,
        job_id: UUID | None = None,
        admin_user_id: UUID | None = None,
        comment: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> CreditTransaction:
        row = await self._fetchrow(
            """INSERT INTO credit_transactions
               (user_id, amount, credit_type, reason, balance_after,
                job_id, admin_user_id, comment)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING *""",
            user_id,
            amount,
            credit_type,
            reason,
            balance_after,
            job_id,
            admin_user_id,
            comment,
            conn=conn,
        )
        return CreditTransaction(**dict(row))

    async def get_charges_for_job(
        self, job_id: UUID, *, conn: asyncpg.Connection | None = None
    ) -> list[CreditTransaction]:
        rows = await self._fetch(
            """SELECT * FROM credit_transactions
               WHERE job_id = $1 AND reason = 'job_charge'
               ORDER BY created_at""",
            job_id,
            conn=conn,
        )
        return [CreditTransaction(**dict(r)) for r in rows]
