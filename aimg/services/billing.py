from __future__ import annotations

from uuid import UUID

import asyncpg

from aimg.db.repos.credit_transactions import CreditTransactionRepo
from aimg.db.repos.users import UserRepo


def calculate_credit_split(
    free_credits: int, paid_credits: int, cost: int
) -> tuple[int, int]:
    """Returns (free_deduction, paid_deduction). Raises ValueError if insufficient."""
    total = free_credits + paid_credits
    if total < cost:
        raise ValueError(f"Insufficient credits: need {cost}, have {total}")
    free_deduction = min(cost, free_credits)
    paid_deduction = cost - free_deduction
    return free_deduction, paid_deduction


async def reserve_credits(
    pool: asyncpg.Pool,
    conn: asyncpg.Connection,
    user_id: UUID,
    credit_cost: int,
    job_id: UUID,
) -> None:
    user_repo = UserRepo(pool)
    ct_repo = CreditTransactionRepo(pool)

    user = await user_repo.get_by_id(user_id, conn=conn)
    if not user:
        raise ValueError("User not found")

    free_deduction, paid_deduction = calculate_credit_split(
        user.free_credits, user.paid_credits, credit_cost
    )

    updated = await user_repo.update_credits(
        user_id, -free_deduction, -paid_deduction, conn=conn
    )
    if not updated:
        raise ValueError("Concurrent credit update failed")

    if free_deduction > 0:
        await ct_repo.create(
            user_id=user_id,
            amount=-free_deduction,
            credit_type="free",
            reason="job_charge",
            balance_after=user.free_credits - free_deduction,
            job_id=job_id,
            conn=conn,
        )
    if paid_deduction > 0:
        await ct_repo.create(
            user_id=user_id,
            amount=-paid_deduction,
            credit_type="paid",
            reason="job_charge",
            balance_after=user.paid_credits - paid_deduction,
            job_id=job_id,
            conn=conn,
        )


async def refund_credits(
    pool: asyncpg.Pool,
    conn: asyncpg.Connection,
    job_id: UUID,
    user_id: UUID,
) -> None:
    ct_repo = CreditTransactionRepo(pool)
    user_repo = UserRepo(pool)

    charges = await ct_repo.get_charges_for_job(job_id, conn=conn)
    if not charges:
        return

    free_refund = 0
    paid_refund = 0
    for charge in charges:
        if charge.credit_type == "free":
            free_refund += abs(charge.amount)
        else:
            paid_refund += abs(charge.amount)

    if free_refund > 0 or paid_refund > 0:
        await user_repo.update_credits(
            user_id, free_refund, paid_refund, conn=conn
        )

        user = await user_repo.get_by_id(user_id, conn=conn)
        if free_refund > 0:
            await ct_repo.create(
                user_id=user_id,
                amount=free_refund,
                credit_type="free",
                reason="refund",
                balance_after=user.free_credits,
                job_id=job_id,
                conn=conn,
            )
        if paid_refund > 0:
            await ct_repo.create(
                user_id=user_id,
                amount=paid_refund,
                credit_type="paid",
                reason="refund",
                balance_after=user.paid_credits,
                job_id=job_id,
                conn=conn,
            )
