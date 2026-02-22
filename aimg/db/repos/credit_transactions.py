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
        external_transaction_id: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> CreditTransaction:
        row = await self._fetchrow(
            """INSERT INTO credit_transactions
               (user_id, amount, credit_type, reason, balance_after,
                job_id, admin_user_id, comment, external_transaction_id)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING *""",
            user_id,
            amount,
            credit_type,
            reason,
            balance_after,
            job_id,
            admin_user_id,
            comment,
            external_transaction_id,
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

    async def get_by_external_txn_id(
        self,
        user_id: UUID,
        external_txn_id: str,
        *,
        conn: asyncpg.Connection | None = None,
    ) -> CreditTransaction | None:
        row = await self._fetchrow(
            """SELECT * FROM credit_transactions
               WHERE user_id = $1 AND external_transaction_id = $2""",
            user_id,
            external_txn_id,
            conn=conn,
        )
        return CreditTransaction(**dict(row)) if row else None

    async def get_latest_balances(
        self, *, conn: asyncpg.Connection | None = None
    ) -> list[dict]:
        rows = await self._fetch(
            """SELECT DISTINCT ON (user_id, credit_type)
                      user_id, credit_type, balance_after
               FROM credit_transactions
               ORDER BY user_id, credit_type, created_at DESC""",
            conn=conn,
        )
        return [dict(r) for r in rows]
