"""Tests for job_attempts repo CRUD operations.

Spec reference: 06-business-logic.md Section 16 — job_attempts recording
during provider fallback chain execution.
"""
from datetime import UTC, datetime

from aimg.db.repos.integrations import IntegrationRepo
from aimg.db.repos.job_attempts import JobAttemptRepo
from aimg.db.repos.job_types import JobTypeRepo
from aimg.db.repos.jobs import JobRepo
from aimg.db.repos.partners import PartnerRepo
from aimg.db.repos.providers import ProviderRepo
from aimg.db.repos.users import UserRepo


async def _seed_job(db_pool):
    partner = await PartnerRepo(db_pool).create("JA Partner")
    integ = await IntegrationRepo(db_pool).create(partner.id, "JA Integration")
    user = await UserRepo(db_pool).get_or_create(integ.id, "ja-user-1")
    jt = await JobTypeRepo(db_pool).upsert("ja_test", "JA Test", None, {}, {})
    provider = await ProviderRepo(db_pool).create(
        "ja-prov", "JA Provider", "mock.Class", "enc",
    )
    job = await JobRepo(db_pool).create(integ.id, user.id, jt.id, {}, 1)
    return job, provider


async def test_create_success_attempt(db_pool):
    job, provider = await _seed_job(db_pool)
    repo = JobAttemptRepo(db_pool)

    now = datetime.now(UTC)
    attempt = await repo.create(
        job_id=job.id,
        provider_id=provider.id,
        attempt_number=1,
        status="success",
        started_at=now,
        completed_at=now,
    )
    assert attempt.status == "success"
    assert attempt.attempt_number == 1
    assert attempt.error_code is None


async def test_create_failure_attempt(db_pool):
    job, provider = await _seed_job(db_pool)
    repo = JobAttemptRepo(db_pool)

    now = datetime.now(UTC)
    attempt = await repo.create(
        job_id=job.id,
        provider_id=provider.id,
        attempt_number=1,
        status="failure",
        started_at=now,
        error_code="PROVIDER_ERROR",
        error_message="Connection timeout",
        completed_at=now,
    )
    assert attempt.status == "failure"
    assert attempt.error_code == "PROVIDER_ERROR"
    assert attempt.error_message == "Connection timeout"


async def test_list_by_job_ordered(db_pool):
    job, provider = await _seed_job(db_pool)
    p2 = await ProviderRepo(db_pool).create(
        "ja-prov2", "JA Provider2", "mock.Class", "enc",
    )
    repo = JobAttemptRepo(db_pool)

    now = datetime.now(UTC)
    await repo.create(
        job.id, provider.id, 1, "failure", now,
        error_code="ERR1", error_message="First fail",
    )
    await repo.create(
        job.id, p2.id, 2, "success", now, completed_at=now,
    )

    attempts = await repo.list_by_job(job.id)
    assert len(attempts) == 2
    assert attempts[0].attempt_number == 1
    assert attempts[0].status == "failure"
    assert attempts[1].attempt_number == 2
    assert attempts[1].status == "success"


async def test_list_by_job_empty(db_pool):
    job, _ = await _seed_job(db_pool)
    repo = JobAttemptRepo(db_pool)

    attempts = await repo.list_by_job(job.id)
    assert attempts == []
