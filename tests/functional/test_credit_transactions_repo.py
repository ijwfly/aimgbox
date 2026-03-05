"""Tests for credit_transactions repo operations and balance reconciliation.

Spec reference: 06-business-logic.md, Section 17
- credit_transactions is the single source of truth
- Two-phase reservation (charge, refund)
- Balance reconciliation via get_latest_balances
"""
from uuid import uuid4

from aimg.db.repos.credit_transactions import CreditTransactionRepo
from aimg.db.repos.integrations import IntegrationRepo
from aimg.db.repos.job_types import JobTypeRepo
from aimg.db.repos.jobs import JobRepo
from aimg.db.repos.partners import PartnerRepo
from aimg.db.repos.users import UserRepo


async def _seed_user(db_pool, free_credits=10):
    partner = await PartnerRepo(db_pool).create("CT Test Partner")
    integ = await IntegrationRepo(db_pool).create(partner.id, "CT Integration")
    user = await UserRepo(db_pool).get_or_create(
        integ.id, f"ct-user-{uuid4().hex[:8]}", default_free_credits=free_credits,
    )
    return partner, integ, user


async def test_create_charge_transaction(db_pool):
    partner, integ, user = await _seed_user(db_pool)
    jt = await JobTypeRepo(db_pool).upsert("ct_test", "CT Test", None, {}, {})
    job = await JobRepo(db_pool).create(integ.id, user.id, jt.id, {}, 1)

    repo = CreditTransactionRepo(db_pool)
    ct = await repo.create(
        user_id=user.id,
        amount=-2,
        credit_type="free",
        reason="job_charge",
        balance_after=8,
        job_id=job.id,
    )
    assert ct.amount == -2
    assert ct.credit_type == "free"
    assert ct.reason == "job_charge"
    assert ct.balance_after == 8
    assert ct.job_id == job.id


async def test_create_topup_transaction(db_pool):
    _, _, user = await _seed_user(db_pool)

    repo = CreditTransactionRepo(db_pool)
    ct = await repo.create(
        user_id=user.id,
        amount=50,
        credit_type="paid",
        reason="topup",
        balance_after=50,
        external_transaction_id="stripe_123",
    )
    assert ct.amount == 50
    assert ct.reason == "topup"
    assert ct.external_transaction_id == "stripe_123"


async def test_create_refund_transaction(db_pool):
    partner, integ, user = await _seed_user(db_pool)
    jt = await JobTypeRepo(db_pool).upsert("ct_ref", "CT Ref", None, {}, {})
    job = await JobRepo(db_pool).create(integ.id, user.id, jt.id, {}, 1)

    repo = CreditTransactionRepo(db_pool)

    # Charge
    await repo.create(
        user_id=user.id, amount=-3, credit_type="free",
        reason="job_charge", balance_after=7, job_id=job.id,
    )

    # Refund
    refund = await repo.create(
        user_id=user.id, amount=3, credit_type="free",
        reason="refund", balance_after=10, job_id=job.id,
    )
    assert refund.amount == 3
    assert refund.reason == "refund"


async def test_get_charges_for_job(db_pool):
    partner, integ, user = await _seed_user(db_pool)
    jt = await JobTypeRepo(db_pool).upsert("ct_charges", "CT Charges", None, {}, {})
    job = await JobRepo(db_pool).create(integ.id, user.id, jt.id, {}, 1)

    repo = CreditTransactionRepo(db_pool)
    await repo.create(user.id, -2, "free", "job_charge", 8, job_id=job.id)
    await repo.create(user.id, -1, "paid", "job_charge", -1, job_id=job.id)

    charges = await repo.get_charges_for_job(job.id)
    assert len(charges) == 2
    assert all(c.reason == "job_charge" for c in charges)


async def test_get_charges_excludes_refunds(db_pool):
    partner, integ, user = await _seed_user(db_pool)
    jt = await JobTypeRepo(db_pool).upsert("ct_exc", "CT Exc", None, {}, {})
    job = await JobRepo(db_pool).create(integ.id, user.id, jt.id, {}, 1)

    repo = CreditTransactionRepo(db_pool)
    await repo.create(user.id, -2, "free", "job_charge", 8, job_id=job.id)
    await repo.create(user.id, 2, "free", "refund", 10, job_id=job.id)

    charges = await repo.get_charges_for_job(job.id)
    assert len(charges) == 1
    assert charges[0].amount == -2


async def test_get_by_external_txn_id(db_pool):
    _, _, user = await _seed_user(db_pool)
    repo = CreditTransactionRepo(db_pool)

    ct = await repo.create(
        user.id, 100, "paid", "topup", 100,
        external_transaction_id="txn_unique_123",
    )

    found = await repo.get_by_external_txn_id(user.id, "txn_unique_123")
    assert found is not None
    assert found.id == ct.id

    not_found = await repo.get_by_external_txn_id(user.id, "nonexistent")
    assert not_found is None


async def test_list_by_user(db_pool):
    _, _, user = await _seed_user(db_pool)
    repo = CreditTransactionRepo(db_pool)

    await repo.create(user.id, 50, "paid", "topup", 50)
    await repo.create(user.id, -10, "paid", "job_charge", 40)
    await repo.create(user.id, 10, "paid", "refund", 50)

    transactions = await repo.list_by_user(user.id)
    assert len(transactions) == 3


async def test_count_by_user(db_pool):
    _, _, user = await _seed_user(db_pool)
    repo = CreditTransactionRepo(db_pool)

    await repo.create(user.id, 50, "paid", "topup", 50)
    await repo.create(user.id, -10, "paid", "job_charge", 40)

    count = await repo.count_by_user(user.id)
    assert count == 2


async def test_get_latest_balances(db_pool):
    _, _, user = await _seed_user(db_pool)
    repo = CreditTransactionRepo(db_pool)

    # Create sequence of transactions
    await repo.create(user.id, -3, "free", "job_charge", 7)
    await repo.create(user.id, -2, "free", "job_charge", 5)
    await repo.create(user.id, 50, "paid", "topup", 50)
    await repo.create(user.id, -10, "paid", "job_charge", 40)

    balances = await repo.get_latest_balances()
    # Should have one entry per (user_id, credit_type) — the latest
    user_balances = {
        (b["user_id"], b["credit_type"]): b["balance_after"]
        for b in balances if b["user_id"] == user.id
    }
    assert user_balances[(user.id, "free")] == 5
    assert user_balances[(user.id, "paid")] == 40


async def test_admin_adjustment_transaction(db_pool):
    """Admin credit adjustments should be recorded with admin_user_id and comment."""
    _, _, user = await _seed_user(db_pool)
    from aimg.admin.auth import hash_password
    from aimg.db.repos.admin_users import AdminUserRepo
    admin_repo = AdminUserRepo(db_pool)
    admin = await admin_repo.create("adj_admin", hash_password("pw"), "admin")

    repo = CreditTransactionRepo(db_pool)
    ct = await repo.create(
        user_id=user.id,
        amount=25,
        credit_type="paid",
        reason="admin_adjustment",
        balance_after=25,
        admin_user_id=admin.id,
        comment="Compensation for bug",
    )
    assert ct.admin_user_id == admin.id
    assert ct.comment == "Compensation for bug"
    assert ct.reason == "admin_adjustment"
