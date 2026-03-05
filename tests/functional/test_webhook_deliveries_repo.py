"""Tests for webhook_deliveries repo CRUD operations.

Spec reference: 05-api.md Section 15 — Webhook delivery tracking,
retry status management, pending retries.
"""
from datetime import UTC, datetime, timedelta

from aimg.db.repos.integrations import IntegrationRepo
from aimg.db.repos.job_types import JobTypeRepo
from aimg.db.repos.jobs import JobRepo
from aimg.db.repos.partners import PartnerRepo
from aimg.db.repos.users import UserRepo
from aimg.db.repos.webhook_deliveries import WebhookDeliveryRepo


async def _seed(db_pool):
    partner = await PartnerRepo(db_pool).create("WH Test Partner")
    integ = await IntegrationRepo(db_pool).create(
        partner.id, "WH Integration",
        webhook_url="http://example.com/wh",
        webhook_secret="secret",
    )
    user = await UserRepo(db_pool).get_or_create(integ.id, "wh-user-1")
    jt = await JobTypeRepo(db_pool).upsert("wh_test", "WH Test", None, {}, {})
    job = await JobRepo(db_pool).create(integ.id, user.id, jt.id, {}, 1)
    return integ, job


async def test_create_webhook_delivery(db_pool):
    integ, job = await _seed(db_pool)
    repo = WebhookDeliveryRepo(db_pool)

    delivery = await repo.create(
        integration_id=integ.id,
        job_id=job.id,
        event="job.succeeded",
        payload={"status": "succeeded", "job_id": str(job.id)},
    )
    assert delivery.event == "job.succeeded"
    assert delivery.status == "pending"
    assert delivery.attempts == 0
    assert delivery.integration_id == integ.id
    assert delivery.job_id == job.id


async def test_update_delivery_to_delivered(db_pool):
    integ, job = await _seed(db_pool)
    repo = WebhookDeliveryRepo(db_pool)

    delivery = await repo.create(
        integration_id=integ.id,
        job_id=job.id,
        event="job.succeeded",
        payload={"status": "succeeded"},
    )

    updated = await repo.update_delivery(
        delivery.id,
        status="delivered",
        attempts=1,
        last_status_code=200,
    )
    assert updated is not None
    assert updated.status == "delivered"
    assert updated.attempts == 1
    assert updated.last_status_code == 200


async def test_update_delivery_to_failed(db_pool):
    integ, job = await _seed(db_pool)
    repo = WebhookDeliveryRepo(db_pool)

    delivery = await repo.create(
        integration_id=integ.id,
        job_id=job.id,
        event="job.failed",
        payload={"status": "failed"},
    )

    updated = await repo.update_delivery(
        delivery.id,
        status="failed",
        attempts=3,
        last_status_code=500,
        last_error="Internal Server Error",
    )
    assert updated.status == "failed"
    assert updated.attempts == 3
    assert updated.last_error == "Internal Server Error"


async def test_get_pending_retries(db_pool):
    integ, job = await _seed(db_pool)
    repo = WebhookDeliveryRepo(db_pool)

    past = datetime.now(UTC) - timedelta(minutes=5)
    future = datetime.now(UTC) + timedelta(hours=1)

    # Delivery ready for retry (past next_retry_at)
    ready = await repo.create(
        integration_id=integ.id,
        job_id=job.id,
        event="job.succeeded",
        payload={"status": "succeeded"},
        next_retry_at=past,
    )

    # Delivery not yet ready (future next_retry_at)
    not_ready = await repo.create(
        integration_id=integ.id,
        job_id=job.id,
        event="job.failed",
        payload={"status": "failed"},
        next_retry_at=future,
    )

    pending = await repo.get_pending_retries(datetime.now(UTC))
    pending_ids = [d.id for d in pending]
    assert ready.id in pending_ids
    assert not_ready.id not in pending_ids


async def test_get_pending_retries_excludes_delivered(db_pool):
    integ, job = await _seed(db_pool)
    repo = WebhookDeliveryRepo(db_pool)

    past = datetime.now(UTC) - timedelta(minutes=5)
    delivery = await repo.create(
        integration_id=integ.id,
        job_id=job.id,
        event="job.succeeded",
        payload={},
        next_retry_at=past,
    )

    # Mark as delivered
    await repo.update_delivery(delivery.id, status="delivered", attempts=1)

    pending = await repo.get_pending_retries(datetime.now(UTC))
    assert all(d.id != delivery.id for d in pending)
