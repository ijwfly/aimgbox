from __future__ import annotations

import json
from typing import Annotated

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from aimg.api.dependencies import get_current_integration, get_current_user, get_db_pool, get_redis
from aimg.api.envelope import ApiResponse
from aimg.api.errors import InvalidAmountError, InvalidInputError
from aimg.common.logging import request_id_var
from aimg.db.models import Integration, User
from aimg.db.repos.credit_transactions import CreditTransactionRepo
from aimg.db.repos.job_types import JobTypeRepo
from aimg.db.repos.users import UserRepo

router = APIRouter(prefix="/v1/billing", tags=["billing"])


class TopupRequest(BaseModel):
    external_user_id: str
    amount: int
    external_transaction_id: str
    comment: str | None = None


class CheckRequest(BaseModel):
    job_type: str


@router.post("/topup", status_code=201)
async def topup(
    body: TopupRequest,
    integration: Integration = Depends(get_current_integration),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    redis_client: aioredis.Redis = Depends(get_redis),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    if body.amount <= 0:
        raise InvalidAmountError("Amount must be greater than 0")

    user_repo = UserRepo(db_pool)
    ct_repo = CreditTransactionRepo(db_pool)

    # Idempotency: check Redis key
    if idempotency_key:
        idem_redis_key = f"aimg:idempotency:topup:{integration.id}:{idempotency_key}"
        cached = await redis_client.get(idem_redis_key)
        if cached:
            # Return the cached result
            return json.loads(cached)

    # Get or create user
    user = await user_repo.get_or_create(
        integration.id,
        body.external_user_id,
        default_free_credits=integration.default_free_credits,
    )

    # Check DB-level idempotency via external_transaction_id
    existing = await ct_repo.get_by_external_txn_id(
        user.id, body.external_transaction_id
    )
    if existing:
        updated_user = await user_repo.get_by_id(user.id)
        rid = request_id_var.get() or ""
        result = ApiResponse(
            request_id=rid,
            success=True,
            data={
                "user_id": str(user.id),
                "external_user_id": body.external_user_id,
                "paid_credits": updated_user.paid_credits if updated_user else user.paid_credits,
                "transaction_id": str(existing.id),
            },
        ).model_dump(mode="json")
        return result

    # Transaction: update credits + create transaction record
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            updated = await user_repo.update_credits(
                user.id, 0, body.amount, conn=conn
            )
            if not updated:
                raise InvalidAmountError("Failed to update credits")

            updated_user = await user_repo.get_by_id(user.id, conn=conn)
            txn = await ct_repo.create(
                user_id=user.id,
                amount=body.amount,
                credit_type="paid",
                reason="topup",
                balance_after=updated_user.paid_credits if updated_user else body.amount,
                comment=body.comment,
                external_transaction_id=body.external_transaction_id,
                conn=conn,
            )

    rid = request_id_var.get() or ""
    result = ApiResponse(
        request_id=rid,
        success=True,
        data={
            "user_id": str(user.id),
            "external_user_id": body.external_user_id,
            "paid_credits": updated_user.paid_credits if updated_user else body.amount,
            "transaction_id": str(txn.id),
        },
    ).model_dump(mode="json")

    # Cache idempotency key
    if idempotency_key:
        idem_redis_key = f"aimg:idempotency:topup:{integration.id}:{idempotency_key}"
        await redis_client.setex(idem_redis_key, 86400, json.dumps(result, default=str))

    return result


@router.post("/check")
async def check(
    body: CheckRequest,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> dict:
    jt_repo = JobTypeRepo(db_pool)
    job_type = await jt_repo.get_by_slug(body.job_type)
    if not job_type:
        raise InvalidInputError(f"Unknown job type: {body.job_type}")

    total = user.free_credits + user.paid_credits
    rid = request_id_var.get() or ""
    return ApiResponse(
        request_id=rid,
        success=True,
        data={
            "can_afford": total >= job_type.credit_cost,
            "credit_cost": job_type.credit_cost,
            "free_credits": user.free_credits,
            "paid_credits": user.paid_credits,
            "total_credits": total,
        },
    ).model_dump(mode="json")
