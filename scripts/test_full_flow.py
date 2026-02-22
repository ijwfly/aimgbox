#!/usr/bin/env python3
"""
End-to-end test: sets up everything from scratch and runs a job.

Usage:
    uv run python scripts/test_full_flow.py

Expects docker-compose services running (postgres:5433, redis:6379, api:8010, worker).
Migrations must be applied.
"""
import asyncio
import json
import sys
import time

import asyncpg
import httpx

API_BASE = "http://localhost:8010"
DB_DSN = "postgresql://aimg:aimg@localhost:5433/aimg"
JWT_SECRET = "dev-jwt-secret-change-me"


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog",
    )
    await conn.set_type_codec(
        "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog",
    )


async def setup_db() -> str:
    """Create all entities in DB, return JWT token."""
    # Lazy imports — only need these for setup
    from aimg.admin.auth import hash_password
    from aimg.db.repos.admin_users import AdminUserRepo
    from aimg.db.repos.api_keys import ApiKeyRepo
    from aimg.db.repos.integrations import IntegrationRepo
    from aimg.db.repos.job_types import JobTypeRepo
    from aimg.db.repos.partners import PartnerRepo
    from aimg.db.repos.providers import ProviderRepo
    from aimg.services.auth import generate_api_key, hash_api_key

    pool = await asyncpg.create_pool(dsn=DB_DSN, init=_init_connection)
    try:
        # Partner
        partner = await PartnerRepo(pool).create("Flow Test Partner")
        print(f"  Partner: {partner.id}")

        # Integration (10 free credits)
        integration = await IntegrationRepo(pool).create(
            partner.id, "Flow Test Integration", default_free_credits=10,
        )
        print(f"  Integration: {integration.id}")

        # API key
        token = generate_api_key(
            integration_id=integration.id,
            partner_id=partner.id,
            key_id=integration.id,
            secret=JWT_SECRET,
        )
        key_hash = hash_api_key(token)
        await ApiKeyRepo(pool).create(
            integration_id=integration.id,
            key_hash=key_hash,
            label="flow-test-key",
        )
        print(f"  API Key: ...{token[-20:]}")

        # Mock provider
        provider = await ProviderRepo(pool).create(
            slug=f"mock-flow-{int(time.time())}",
            name="Mock Flow Provider",
            adapter_class="aimg.providers.mock.MockProvider",
            api_key_encrypted="not-needed",
        )
        print(f"  Provider: {provider.id}")

        # Job type: txt2img
        jt = await JobTypeRepo(pool).upsert(
            slug="txt2img",
            name="Text to Image",
            description="Generates an image from text prompt",
            input_schema={
                "type": "object",
                "required": ["prompt"],
                "properties": {
                    "prompt": {"type": "string"},
                    "output_format": {"type": "string", "default": "png"},
                },
            },
            output_schema={
                "type": "object",
                "properties": {"image": {"type": "string", "format": "uuid"}},
            },
        )
        print(f"  Job type: {jt.id} ({jt.slug})")

        # Link provider to job type
        await JobTypeRepo(pool).add_provider(jt.id, provider.id, priority=0)
        print(f"  Linked provider to {jt.slug}")

        # Admin user
        admin_repo = AdminUserRepo(pool)
        if not await admin_repo.get_by_username("admin"):
            pw_hash = hash_password("admin")
            await admin_repo.create("admin", pw_hash, "super_admin")
            print("  Admin user: admin/admin")
        else:
            print("  Admin user: already exists")

        return token
    finally:
        await pool.close()


async def submit_and_wait(token: str) -> None:
    """Submit a job via API, poll until done, print result."""
    headers = {
        "X-API-Key": token,
        "X-External-User-Id": "test-user-1",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(base_url=API_BASE, timeout=30) as client:
        # Submit job
        resp = await client.post(
            "/v1/jobs",
            headers=headers,
            json={"job_type": "txt2img", "input": {"prompt": "a cat in space"}},
        )
        if resp.status_code not in (200, 201):
            print(f"\nFAILED to create job: {resp.status_code}")
            print(resp.text)
            sys.exit(1)

        data = resp.json()["data"]
        job_id = data["job_id"]
        print(f"\n  Job created: {job_id}")
        print(f"  Status: {data['status']}")

        # Poll
        for i in range(30):
            await asyncio.sleep(1)
            resp = await client.get(f"/v1/jobs/{job_id}", headers=headers)
            data = resp.json()["data"]
            status = data["status"]
            sys.stdout.write(f"\r  Polling... {status} ({i + 1}s)")
            sys.stdout.flush()
            if status in ("completed", "succeeded", "failed"):
                print()
                break
        else:
            print("\n  TIMEOUT: job did not finish in 30s")
            sys.exit(1)

    return data


async def main() -> None:
    print("\n=== AIMG Full Flow Test ===\n")

    # Check API is alive
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            resp = await client.get(f"{API_BASE}/health")
            if resp.status_code != 200:
                print(f"API not healthy: {resp.status_code}")
                sys.exit(1)
        except httpx.ConnectError:
            print(f"Cannot connect to API at {API_BASE}")
            print("Make sure docker-compose is running: docker-compose up -d")
            sys.exit(1)
    print("[1/3] API is healthy\n")

    # Setup
    print("[2/3] Setting up entities...")
    token = await setup_db()
    print()

    # Submit job
    print("[3/3] Submitting txt2img job...")
    result = await submit_and_wait(token)

    # Result
    print("\n=== Result ===")
    print(f"  Status:  {result['status']}")
    if result["status"] in ("completed", "succeeded"):
        print(f"  Output:  {result['output']}")
        print(f"  Credits: {result['credit_cost']}")
        print("\n  SUCCESS")
    else:
        print(f"  Error:   {result.get('error')}")
        print("\n  FAILED")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
