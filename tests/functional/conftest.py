import os

import httpx
import pytest

from aimg.api.app import create_app
from aimg.common.connections import create_db_pool, create_redis_client, create_s3_client
from aimg.common.settings import Settings


@pytest.fixture
def settings():
    return Settings(
        database_url=os.environ.get(
            "AIMG_DATABASE_URL", "postgresql://aimg:aimg@localhost:5433/aimg"
        ),
        redis_url=os.environ.get("AIMG_REDIS_URL", "redis://localhost:6379/0"),
        s3_endpoint=os.environ.get("AIMG_S3_ENDPOINT", "http://localhost:9000"),
        s3_access_key=os.environ.get("AIMG_S3_ACCESS_KEY", "minioadmin"),
        s3_secret_key=os.environ.get("AIMG_S3_SECRET_KEY", "minioadmin"),
        s3_bucket=os.environ.get("AIMG_S3_BUCKET", "aimg"),
        jwt_secret="test-jwt-secret",
        encryption_key="test-encryption-key",
        admin_session_secret="test-admin-session-secret",
        log_level="DEBUG",
    )


@pytest.fixture
async def client(settings):
    app = create_app(settings)

    # Manually initialize app state (lifespan not triggered by ASGI transport)
    app.state.settings = settings
    app.state.db_pool = await create_db_pool(settings)
    app.state.redis = create_redis_client(settings)

    s3_cm = create_s3_client(settings)
    app.state.s3_client = await s3_cm.__aenter__()
    app.state._s3_cm = s3_cm

    # Auto-create bucket
    try:
        await app.state.s3_client.head_bucket(Bucket=settings.s3_bucket)
    except Exception:
        await app.state.s3_client.create_bucket(Bucket=settings.s3_bucket)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    # Cleanup
    await app.state.db_pool.close()
    await app.state.redis.aclose()
    await s3_cm.__aexit__(None, None, None)
