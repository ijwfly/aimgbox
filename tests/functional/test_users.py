import pytest


@pytest.mark.asyncio
async def test_balance(client, seeded_data):
    headers = {
        "X-API-Key": seeded_data["token"],
        "X-External-User-Id": "balance-test-user",
    }
    resp = await client.get("/v1/users/me/balance", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["external_user_id"] == "balance-test-user"
    assert data["free_credits"] == 10  # default from integration
    assert data["paid_credits"] == 0
    assert data["total_credits"] == 10


@pytest.mark.asyncio
async def test_history_empty(client, seeded_data):
    headers = {
        "X-API-Key": seeded_data["token"],
        "X-External-User-Id": "history-empty-user",
    }
    resp = await client.get("/v1/users/me/history", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["jobs"] == []
    assert data["has_more"] is False
    assert data["next_cursor"] is None


@pytest.mark.asyncio
async def test_history_with_job(client, seeded_data):
    headers = {
        "X-API-Key": seeded_data["token"],
        "X-External-User-Id": "history-user",
    }
    # Upload a file
    upload_resp = await client.post(
        "/v1/files",
        headers=headers,
        files={"file": ("test.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
    )
    file_id = upload_resp.json()["data"]["file_id"]

    # Create a job
    await client.post(
        "/v1/jobs",
        headers=headers,
        json={"job_type": "remove_bg", "input": {"image": file_id}},
    )

    resp = await client.get("/v1/users/me/history", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["job_type"] == "remove_bg"


@pytest.mark.asyncio
async def test_history_status_filter(client, seeded_data):
    headers = {
        "X-API-Key": seeded_data["token"],
        "X-External-User-Id": "filter-user",
    }
    upload_resp = await client.post(
        "/v1/files",
        headers=headers,
        files={"file": ("test.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
    )
    file_id = upload_resp.json()["data"]["file_id"]

    await client.post(
        "/v1/jobs",
        headers=headers,
        json={"job_type": "remove_bg", "input": {"image": file_id}},
    )

    # Job is pending — filter for succeeded should return empty
    resp = await client.get("/v1/users/me/history?status=succeeded", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]["jobs"]) == 0

    # Filter for pending should return the job
    resp = await client.get("/v1/users/me/history?status=pending", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]["jobs"]) == 1


@pytest.mark.asyncio
async def test_history_pagination(client, seeded_data):
    headers = {
        "X-API-Key": seeded_data["token"],
        "X-External-User-Id": "paginate-user",
    }
    upload_resp = await client.post(
        "/v1/files",
        headers=headers,
        files={"file": ("test.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
    )
    file_id = upload_resp.json()["data"]["file_id"]

    # Create 3 jobs
    for _ in range(3):
        await client.post(
            "/v1/jobs",
            headers=headers,
            json={"job_type": "remove_bg", "input": {"image": file_id}},
        )

    # Page 1: limit=1
    resp = await client.get("/v1/users/me/history?limit=1", headers=headers)
    data = resp.json()["data"]
    assert len(data["jobs"]) == 1
    assert data["has_more"] is True
    assert data["next_cursor"] is not None

    # Page 2: use cursor
    cursor = data["next_cursor"]
    resp2 = await client.get(f"/v1/users/me/history?limit=1&cursor={cursor}", headers=headers)
    data2 = resp2.json()["data"]
    assert len(data2["jobs"]) == 1
    assert data2["has_more"] is True
    # Different job than page 1
    assert data2["jobs"][0]["job_id"] != data["jobs"][0]["job_id"]
