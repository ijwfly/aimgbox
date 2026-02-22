import pytest


@pytest.mark.asyncio
async def test_rate_limit_headers_present(client, seeded_data):
    headers = {
        "X-API-Key": seeded_data["token"],
        "X-External-User-Id": "rl-user",
    }
    resp = await client.get("/v1/meta/job-types", headers=headers)
    assert resp.status_code == 200
    assert "X-RateLimit-Limit" in resp.headers
    assert "X-RateLimit-Remaining" in resp.headers
    assert "X-RateLimit-Reset" in resp.headers


@pytest.mark.asyncio
async def test_rate_limit_exceeded_returns_429(client, seeded_data, db_pool):
    """Set integration RPM to 3, make 4 requests, 4th should get 429."""
    integration = seeded_data["integration"]

    # Lower the RPM limit
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE integrations SET rate_limit_rpm = 3 WHERE id = $1",
            integration.id,
        )

    headers = {
        "X-API-Key": seeded_data["token"],
        "X-External-User-Id": "rl-user-2",
    }

    for i in range(3):
        resp = await client.get("/v1/meta/job-types", headers=headers)
        assert resp.status_code == 200, f"Request {i+1} failed with {resp.status_code}"

    # 4th request should be rate limited
    resp = await client.get("/v1/meta/job-types", headers=headers)
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert resp.json()["error"]["code"] == "RATE_LIMITED"
