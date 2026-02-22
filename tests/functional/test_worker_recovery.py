from datetime import UTC, datetime, timedelta

import pytest

from aimg.common.connections import create_redis_client
from aimg.db.repos.jobs import JobRepo
from aimg.db.repos.users import UserRepo
from aimg.worker.main import QUEUE_KEY, recover_orphaned_jobs


@pytest.mark.asyncio
async def test_orphaned_pending_job_requeued(db_pool, seeded_data, settings):
    """Pending jobs older than 60s should be re-enqueued."""
    user_repo = UserRepo(db_pool)

    integration = seeded_data["integration"]
    job_type = seeded_data["job_type"]

    user = await user_repo.get_or_create(
        integration.id, "recovery-user", default_free_credits=10
    )

    # Create a pending job with old created_at
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO jobs
               (integration_id, user_id, job_type_id, input_data,
                credit_charged, created_at)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
            integration.id,
            user.id,
            job_type.id,
            {"test": True},
            1,
            datetime.now(UTC) - timedelta(seconds=120),
        )
    old_job_id = str(row["id"])

    redis_client = create_redis_client(settings)
    try:
        await recover_orphaned_jobs(db_pool, redis_client)

        # Check that job was enqueued
        queue_len = await redis_client.llen(QUEUE_KEY)
        assert queue_len >= 1

        # Verify the specific job ID is in the queue
        items = await redis_client.lrange(QUEUE_KEY, 0, -1)
        job_ids = [item for item in items]
        assert old_job_id.encode() in job_ids or old_job_id in [
            i.decode() if isinstance(i, bytes) else i for i in job_ids
        ]
    finally:
        await redis_client.flushdb()
        await redis_client.aclose()


@pytest.mark.asyncio
async def test_stuck_running_job_failed_by_janitor(db_pool, seeded_data, settings):
    """Running jobs past timeout+60s should be marked as failed."""
    import asyncio

    from aimg.worker.main import recovery_janitor_loop

    job_repo = JobRepo(db_pool)
    user_repo = UserRepo(db_pool)

    integration = seeded_data["integration"]
    job_type = seeded_data["job_type"]  # timeout_seconds = 300

    user = await user_repo.get_or_create(
        integration.id, "janitor-user", default_free_credits=10
    )

    # Create a running job with very old started_at
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO jobs
               (integration_id, user_id, job_type_id, input_data,
                credit_charged, status, started_at)
               VALUES ($1, $2, $3, $4, $5, 'running', $6) RETURNING *""",
            integration.id,
            user.id,
            job_type.id,
            {"test": True},
            0,  # 0 charged so refund doesn't fail
            datetime.now(UTC) - timedelta(seconds=500),
        )
    stuck_job_id = row["id"]

    # Run janitor once (with very short interval, and immediate shutdown)
    shutdown_event = asyncio.Event()

    # Use a modified settings with short recovery interval
    settings_copy = settings.model_copy(update={"worker_recovery_interval": 0})

    # Start janitor and let it run one cycle
    task = asyncio.create_task(
        recovery_janitor_loop(db_pool, settings_copy, shutdown_event)
    )
    await asyncio.sleep(0.5)
    shutdown_event.set()
    await task

    # Check job is now failed
    job = await job_repo.get_by_id(stuck_job_id)
    assert job is not None
    assert job.status == "failed"
    assert job.error_code == "TIMEOUT"
