async def test_valid_api_key(client, seeded_data):
    token = seeded_data["token"]
    resp = await client.get(
        "/v1/files/00000000-0000-0000-0000-000000000000",
        headers={
            "X-API-Key": token,
            "X-External-User-Id": "user1",
        },
    )
    # Should get 404 (file not found) not 401 — auth passed
    assert resp.status_code == 404


async def test_missing_api_key(client):
    resp = await client.get(
        "/v1/files/00000000-0000-0000-0000-000000000000",
        headers={"X-External-User-Id": "user1"},
    )
    assert resp.status_code == 422  # FastAPI validation for missing header


async def test_invalid_api_key(client):
    resp = await client.get(
        "/v1/files/00000000-0000-0000-0000-000000000000",
        headers={
            "X-API-Key": "invalid-token",
            "X-External-User-Id": "user1",
        },
    )
    assert resp.status_code == 401


async def test_revoked_api_key(client, seeded_data, db_pool):
    """Revoke key in DB, verify 401."""
    api_key = seeded_data["api_key"]

    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE api_keys SET is_revoked = true, revoked_at = now() WHERE id = $1",
            api_key.id,
        )

    resp = await client.get(
        "/v1/files/00000000-0000-0000-0000-000000000000",
        headers={
            "X-API-Key": seeded_data["token"],
            "X-External-User-Id": "user1",
        },
    )
    assert resp.status_code == 401
