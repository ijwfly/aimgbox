import pytest


@pytest.mark.asyncio
async def test_idempotent_same_key_returns_200(client, seeded_data):
    headers = {
        "X-API-Key": seeded_data["token"],
        "X-External-User-Id": "idem-user",
        "Idempotency-Key": "unique-key-123",
    }

    # Upload a file first
    resp = await client.post(
        "/v1/files",
        headers=headers,
        files={"file": ("test.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
    )
    assert resp.status_code == 201
    file_id = resp.json()["data"]["file_id"]

    # First request: 201 Created
    body = {"job_type": "remove_bg", "input": {"image": file_id}}
    r1 = await client.post("/v1/jobs", headers=headers, json=body)
    assert r1.status_code == 201
    job_id_1 = r1.json()["data"]["job_id"]

    # Second request with same key: 200 OK, same job_id
    r2 = await client.post("/v1/jobs", headers=headers, json=body)
    assert r2.status_code == 200
    assert r2.json()["data"]["job_id"] == job_id_1


@pytest.mark.asyncio
async def test_different_key_creates_new_job(client, seeded_data):
    headers = {
        "X-API-Key": seeded_data["token"],
        "X-External-User-Id": "idem-user-2",
    }

    resp = await client.post(
        "/v1/files",
        headers=headers,
        files={"file": ("test.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
    )
    file_id = resp.json()["data"]["file_id"]
    body = {"job_type": "remove_bg", "input": {"image": file_id}}

    r1 = await client.post(
        "/v1/jobs",
        headers={**headers, "Idempotency-Key": "key-a"},
        json=body,
    )
    r2 = await client.post(
        "/v1/jobs",
        headers={**headers, "Idempotency-Key": "key-b"},
        json=body,
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["data"]["job_id"] != r2.json()["data"]["job_id"]


@pytest.mark.asyncio
async def test_no_key_always_creates_new(client, seeded_data):
    headers = {
        "X-API-Key": seeded_data["token"],
        "X-External-User-Id": "idem-user-3",
    }

    resp = await client.post(
        "/v1/files",
        headers=headers,
        files={"file": ("test.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
    )
    file_id = resp.json()["data"]["file_id"]
    body = {"job_type": "remove_bg", "input": {"image": file_id}}

    r1 = await client.post("/v1/jobs", headers=headers, json=body)
    r2 = await client.post("/v1/jobs", headers=headers, json=body)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["data"]["job_id"] != r2.json()["data"]["job_id"]
