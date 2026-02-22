
import pytest

from aimg.db.repos.webhook_deliveries import WebhookDeliveryRepo
from aimg.worker.main import process_job


@pytest.mark.asyncio
async def test_webhook_delivery_created_on_job_completion(
    client, seeded_data, db_pool, settings
):
    """When a job completes, a webhook_deliveries record should be created."""
    headers = {
        "X-API-Key": seeded_data["token"],
        "X-External-User-Id": "wh-user-1",
    }

    # Upload file
    resp = await client.post(
        "/v1/files",
        headers=headers,
        files={"file": ("test.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
    )
    file_id = resp.json()["data"]["file_id"]

    # Create job
    resp = await client.post(
        "/v1/jobs",
        headers=headers,
        json={"job_type": "remove_bg", "input": {"image": file_id}},
    )
    assert resp.status_code == 201
    job_id = resp.json()["data"]["job_id"]

    # Process job via worker
    from uuid import UUID

    from aimg.common.connections import create_redis_client, create_s3_client

    redis_client = create_redis_client(settings)
    async with create_s3_client(settings) as s3_client:
        try:
            await s3_client.head_bucket(Bucket=settings.s3_bucket)
        except Exception:
            await s3_client.create_bucket(Bucket=settings.s3_bucket)
        from aimg.jobs.registry import discover_handlers

        discover_handlers()
        await process_job(UUID(job_id), db_pool, redis_client, s3_client, settings)

    await redis_client.aclose()

    # Check webhook delivery was created
    wd_repo = WebhookDeliveryRepo(db_pool)
    rows = await wd_repo._fetch(
        "SELECT * FROM webhook_deliveries WHERE job_id = $1",
        UUID(job_id),
    )
    assert len(rows) >= 1
    delivery = dict(rows[0])
    assert delivery["event"] == "job.succeeded"


@pytest.mark.asyncio
async def test_no_webhook_without_url(client, seeded_data, db_pool, settings):
    """Integration without webhook_url should not create delivery records."""
    # Remove webhook URL
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE integrations SET webhook_url = NULL WHERE id = $1",
            seeded_data["integration"].id,
        )

    headers = {
        "X-API-Key": seeded_data["token"],
        "X-External-User-Id": "wh-user-no-url",
    }

    resp = await client.post(
        "/v1/files",
        headers=headers,
        files={"file": ("test.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
    )
    file_id = resp.json()["data"]["file_id"]

    resp = await client.post(
        "/v1/jobs",
        headers=headers,
        json={"job_type": "remove_bg", "input": {"image": file_id}},
    )
    job_id = resp.json()["data"]["job_id"]

    from uuid import UUID

    from aimg.common.connections import create_redis_client, create_s3_client

    redis_client = create_redis_client(settings)
    async with create_s3_client(settings) as s3_client:
        try:
            await s3_client.head_bucket(Bucket=settings.s3_bucket)
        except Exception:
            await s3_client.create_bucket(Bucket=settings.s3_bucket)
        from aimg.jobs.registry import discover_handlers

        discover_handlers()
        await process_job(UUID(job_id), db_pool, redis_client, s3_client, settings)

    await redis_client.aclose()

    wd_repo = WebhookDeliveryRepo(db_pool)
    rows = await wd_repo._fetch(
        "SELECT * FROM webhook_deliveries WHERE job_id = $1",
        UUID(job_id),
    )
    assert len(rows) == 0
