import asyncio
import os

from aimg.common.connections import create_db_pool
from aimg.common.encryption import encrypt_value
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

        # Create Replicate provider
        replicate_token = os.environ.get("REPLICATE_API_TOKEN", "")
        if replicate_token:
            replicate_key_enc = encrypt_value(replicate_token, settings.encryption_key)
        else:
            replicate_key_enc = "not-needed"
            print("WARNING: REPLICATE_API_TOKEN not set, using placeholder")

        replicate_provider = await provider_repo.create(
            slug="replicate",
            name="Replicate",
            adapter_class="aimg.providers.replicate.ReplicateAdapter",
            api_key_encrypted=replicate_key_enc,
        )
        print(f"Provider: {replicate_provider.id} ({replicate_provider.slug})")

        # Create txt2img job type
        txt2img_type = await jt_repo.upsert(
            slug="txt2img",
            name="Text to Image",
            description="Generates an image from a text prompt using AI",
            input_schema={
                "type": "object",
                "required": ["prompt"],
                "properties": {
                    "prompt": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "negative_prompt": {"type": "string", "default": ""},
                    "width": {"type": "integer", "default": 1024, "minimum": 256, "maximum": 4096},
                    "height": {"type": "integer", "default": 1024, "minimum": 256, "maximum": 4096},
                    "output_format": {
                        "type": "string",
                        "enum": ["png", "webp", "jpg"],
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
        print(f"Job Type: {txt2img_type.id} ({txt2img_type.slug})")

        # Link Replicate to remove_bg (priority 0) + mock as fallback (priority 1)
        await jt_repo.add_provider(
            job_type.id,
            replicate_provider.id,
            priority=0,
            config_override={
                "model": "cjwbw/rembg",
                "version": "fb8af171cfa1616ddcf1242c093f9c46bcada5ad4cf6f2fbe8b81b330ec5c003",
            },
        )
        await jt_repo.add_provider(job_type.id, provider.id, priority=1)
        print(f"Linked providers to {job_type.slug}: replicate(0), mock(1)")

        # Link Replicate to txt2img (priority 0) + mock as fallback (priority 1)
        await jt_repo.add_provider(
            txt2img_type.id,
            replicate_provider.id,
            priority=0,
            config_override={
                "model": "stability-ai/sdxl",
                "version": "7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc",
            },
        )
        await jt_repo.add_provider(txt2img_type.id, provider.id, priority=1)
        print(f"Linked providers to {txt2img_type.slug}: replicate(0), mock(1)")

        print("\n--- Seed complete ---")
        print(f"Use this API key: {token}")
    finally:
        await db_pool.close()


def main() -> None:
    asyncio.run(run_seed())
