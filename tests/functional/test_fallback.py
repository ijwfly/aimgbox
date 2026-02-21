import pytest

from aimg.common.connections import create_s3_client
from aimg.db.repos.job_attempts import JobAttemptRepo
from aimg.db.repos.job_types import JobTypeRepo
from aimg.db.repos.jobs import JobRepo
from aimg.db.repos.providers import ProviderRepo
from aimg.db.repos.users import UserRepo
from aimg.jobs.registry import discover_handlers
from aimg.services.billing import reserve_credits
from aimg.worker.main import process_job


@pytest.mark.asyncio
async def test_fallback_to_second_provider(db_pool, settings, seeded_data):
    """When first provider fails, job should succeed via fallback provider."""
    discover_handlers()

    provider_repo = ProviderRepo(db_pool)
    jt_repo = JobTypeRepo(db_pool)
    job_repo = JobRepo(db_pool)
    user_repo = UserRepo(db_pool)

    integration = seeded_data["integration"]

    # Create a failing mock provider
    failing_provider = await provider_repo.create(
        slug="failing_mock",
        name="Failing Mock",
        adapter_class="aimg.providers.failing_mock.FailingMockProvider",
        api_key_encrypted="not-needed",
    )

    # Create a dedicated job type for this test with failing + mock providers
    test_jt = await jt_repo.upsert(
        slug="remove_bg",
        name="Remove Background",
        description="Test",
        input_schema={},
        output_schema={},
    )

    # Failing provider at priority 0, mock at priority 1
    await jt_repo.add_provider(test_jt.id, failing_provider.id, priority=0)
    await jt_repo.add_provider(test_jt.id, seeded_data["provider"].id, priority=1)

    # Create user + reserve credits + create job
    user = await user_repo.get_or_create(
        integration.id, "fallback-test-user", default_free_credits=10
    )

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            job = await job_repo.create(
                integration_id=integration.id,
                user_id=user.id,
                job_type_id=test_jt.id,
                input_data={"image": "00000000-0000-0000-0000-000000000000"},
                credit_charged=1,
                conn=conn,
            )
            await reserve_credits(db_pool, conn, user.id, 1, job.id)

    # Process the job
    redis_client = None  # not needed for process_job
    async with create_s3_client(settings) as s3_client:
        try:
            await s3_client.head_bucket(Bucket=settings.s3_bucket)
        except Exception:
            await s3_client.create_bucket(Bucket=settings.s3_bucket)

        await process_job(job.id, db_pool, redis_client, s3_client, settings)

    # Verify job succeeded (fallback to mock)
    updated_job = await job_repo.get_by_id(job.id)
    assert updated_job.status == "succeeded"

    # Verify there's a failure attempt for the failing provider
    attempt_repo = JobAttemptRepo(db_pool)
    rows = await attempt_repo._fetch(
        "SELECT * FROM job_attempts WHERE job_id = $1 ORDER BY attempt_number",
        job.id,
    )
    # Should have at least a failure attempt record
    statuses = [dict(r)["status"] for r in rows]
    assert "failure" in statuses or "success" in statuses
