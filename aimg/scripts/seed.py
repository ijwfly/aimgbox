import asyncio

from aimg.common.connections import create_db_pool
from aimg.common.settings import Settings
from aimg.db.repos.api_keys import ApiKeyRepo
from aimg.db.repos.integrations import IntegrationRepo
from aimg.db.repos.job_types import JobTypeRepo
from aimg.db.repos.partners import PartnerRepo
from aimg.db.repos.providers import ProviderRepo
from aimg.services.auth import generate_api_key, hash_api_key


async def run_seed() -> None:
    settings = Settings()
    db_pool = await create_db_pool(settings)

    try:
        partner_repo = PartnerRepo(db_pool)
        integration_repo = IntegrationRepo(db_pool)
        api_key_repo = ApiKeyRepo(db_pool)
        provider_repo = ProviderRepo(db_pool)
        jt_repo = JobTypeRepo(db_pool)

        # Create partner
        partner = await partner_repo.create("Test Partner")
        print(f"Partner: {partner.id} ({partner.name})")

        # Create integration
        integration = await integration_repo.create(
            partner.id, "Test Integration", default_free_credits=10
        )
        print(f"Integration: {integration.id} ({integration.name})")

        # Create API key
        token = generate_api_key(
            integration_id=integration.id,
            partner_id=partner.id,
            key_id=integration.id,  # use integration id as placeholder key_id
            secret=settings.jwt_secret,
        )
        key_hash = hash_api_key(token)
        api_key = await api_key_repo.create(
            integration_id=integration.id,
            key_hash=key_hash,
            label="seed-key",
        )
        print(f"API Key ID: {api_key.id}")
        print(f"JWT Token: {token}")

        # Create mock provider
        provider = await provider_repo.create(
            slug="mock",
            name="Mock Provider",
            adapter_class="aimg.providers.mock.MockProvider",
            api_key_encrypted="not-needed",
        )
        print(f"Provider: {provider.id} ({provider.slug})")

        # Create remove_bg job type
        job_type = await jt_repo.upsert(
            slug="remove_bg",
            name="Remove Background",
            description="Removes background from an image using AI",
            input_schema={
                "type": "object",
                "required": ["image"],
                "properties": {
                    "image": {"type": "string", "format": "uuid"},
                    "output_format": {
                        "type": "string",
                        "enum": ["png", "webp"],
                        "default": "png",
                    },
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "image": {"type": "string", "format": "uuid"},
                },
            },
        )
        print(f"Job Type: {job_type.id} ({job_type.slug})")

        # Link provider to job type
        await jt_repo.add_provider(job_type.id, provider.id, priority=0)
        print(f"Linked provider {provider.slug} to job type {job_type.slug}")

        print("\n--- Seed complete ---")
        print(f"Use this API key: {token}")
    finally:
        await db_pool.close()


def main() -> None:
    asyncio.run(run_seed())
