import os

import httpx
import pytest

from aimg.api.app import create_app
from aimg.common.connections import create_db_pool, create_redis_client, create_s3_client
from aimg.common.i18n import load_locales
from aimg.common.settings import Settings
from aimg.db.repos.api_keys import ApiKeyRepo
from aimg.db.repos.integrations import IntegrationRepo
from aimg.db.repos.job_types import JobTypeRepo
from aimg.db.repos.partners import PartnerRepo
from aimg.db.repos.providers import ProviderRepo
from aimg.services.auth import generate_api_key, hash_api_key


@pytest.fixture(autouse=True, scope="session")
def _load_locales():
    load_locales()


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
        s3_bucket=os.environ.get("AIMG_S3_BUCKET", "aimg-test"),
        jwt_secret="test-jwt-secret-that-is-long-enough",
        encryption_key="test-encryption-key",
        admin_session_secret="test-admin-session-secret",
        log_level="DEBUG",
    )


@pytest.fixture
async def db_pool(settings):
    pool = await create_db_pool(settings)
    yield pool
    await pool.close()


@pytest.fixture
async def redis_client(settings):
    client = create_redis_client(settings)
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture(autouse=True)
async def cleanup_db(db_pool):
    yield
    async with db_pool.acquire() as conn:
        await conn.execute("""
            TRUNCATE webhook_deliveries, credit_transactions,
                     job_attempts, jobs, files, job_type_providers,
                     users, api_keys, integrations, job_types,
                     providers, partners
            CASCADE
        """)


@pytest.fixture
async def client(settings):
    app = create_app(settings)

    app.state.settings = settings
    app.state.db_pool = await create_db_pool(settings)
    app.state.redis = create_redis_client(settings)

    s3_cm = create_s3_client(settings)
    app.state.s3_client = await s3_cm.__aenter__()
    app.state._s3_cm = s3_cm

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


@pytest.fixture
async def seeded_data(db_pool, settings):
    """Create partner, integration, API key, mock provider, and remove_bg job type."""
    partner_repo = PartnerRepo(db_pool)
    integration_repo = IntegrationRepo(db_pool)
    api_key_repo = ApiKeyRepo(db_pool)
    provider_repo = ProviderRepo(db_pool)
    jt_repo = JobTypeRepo(db_pool)

    partner = await partner_repo.create("Test Partner")
    integration = await integration_repo.create(
        partner.id, "Test Integration", default_free_credits=10,
        webhook_url="http://localhost:8888/webhook",
        webhook_secret="test-webhook-secret",
    )

    token = generate_api_key(
        integration_id=integration.id,
        partner_id=partner.id,
        key_id=integration.id,
        secret=settings.jwt_secret,
    )
    key_hash = hash_api_key(token)
    api_key = await api_key_repo.create(
        integration_id=integration.id,
        key_hash=key_hash,
        label="test-key",
    )

    provider = await provider_repo.create(
        slug="mock",
        name="Mock Provider",
        adapter_class="aimg.providers.mock.MockProvider",
        api_key_encrypted="not-needed",
    )

    job_type = await jt_repo.upsert(
        slug="remove_bg",
        name="Remove Background",
        description="Removes background from an image using AI",
        input_schema={
            "type": "object",
            "required": ["image"],
            "properties": {
                "image": {"type": "string", "format": "uuid"},
                "output_format": {"type": "string", "enum": ["png", "webp"], "default": "png"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {"image": {"type": "string", "format": "uuid"}},
        },
    )
    await jt_repo.add_provider(job_type.id, provider.id, priority=0)

    txt2img_type = await jt_repo.upsert(
        slug="txt2img",
        name="Text to Image",
        description="Generates an image from a text prompt using AI",
        input_schema={
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {"type": "string"},
                "width": {"type": "integer", "default": 1024},
                "height": {"type": "integer", "default": 1024},
                "output_format": {
                    "type": "string", "enum": ["png", "webp", "jpg"], "default": "png",
                },
            },
        },
        output_schema={
            "type": "object",
            "properties": {"image": {"type": "string", "format": "uuid"}},
        },
    )
    await jt_repo.add_provider(txt2img_type.id, provider.id, priority=0)

    return {
        "partner": partner,
        "integration": integration,
        "api_key": api_key,
        "token": token,
        "provider": provider,
        "job_type": job_type,
        "txt2img_type": txt2img_type,
    }
