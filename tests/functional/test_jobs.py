async def test_create_job(client, seeded_data):
    token = seeded_data["token"]

    # Upload a file first
    upload_resp = await client.post(
        "/v1/files",
        headers={"X-API-Key": token, "X-External-User-Id": "user1"},
        files={"file": ("photo.png", b"fake-image", "image/png")},
    )
    file_id = upload_resp.json()["data"]["file_id"]

    # Create job
    resp = await client.post(
        "/v1/jobs",
        headers={"X-API-Key": token, "X-External-User-Id": "user1"},
        json={
            "job_type": "remove_bg",
            "input": {"image": file_id, "output_format": "png"},
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["status"] == "pending"
    assert body["data"]["job_type"] == "remove_bg"
    assert "job_id" in body["data"]


async def test_get_job(client, seeded_data):
    token = seeded_data["token"]

    # Upload + create job
    upload_resp = await client.post(
        "/v1/files",
        headers={"X-API-Key": token, "X-External-User-Id": "user1"},
        files={"file": ("photo.png", b"fake-image", "image/png")},
    )
    file_id = upload_resp.json()["data"]["file_id"]

    create_resp = await client.post(
        "/v1/jobs",
        headers={"X-API-Key": token, "X-External-User-Id": "user1"},
        json={"job_type": "remove_bg", "input": {"image": file_id}},
    )
    job_id = create_resp.json()["data"]["job_id"]

    # Get job
    resp = await client.get(
        f"/v1/jobs/{job_id}",
        headers={"X-API-Key": token, "X-External-User-Id": "user1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["job_id"] == job_id


async def test_create_job_insufficient_credits(client, seeded_data, db_pool):
    """User with 0 credits should get 402."""
    token = seeded_data["token"]

    # First create user with 0 credits by uploading (triggers get_or_create)
    await client.post(
        "/v1/files",
        headers={"X-API-Key": token, "X-External-User-Id": "broke-user"},
        files={"file": ("photo.png", b"fake", "image/png")},
    )

    # Set credits to 0
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET free_credits = 0, paid_credits = 0"
        )

    file_resp = await client.post(
        "/v1/files",
        headers={"X-API-Key": token, "X-External-User-Id": "broke-user"},
        files={"file": ("photo.png", b"fake", "image/png")},
    )
    file_id = file_resp.json()["data"]["file_id"]

    resp = await client.post(
        "/v1/jobs",
        headers={"X-API-Key": token, "X-External-User-Id": "broke-user"},
        json={"job_type": "remove_bg", "input": {"image": file_id}},
    )
    assert resp.status_code == 402
    body = resp.json()
    assert body["error"]["code"] == "INSUFFICIENT_CREDITS"


async def test_create_job_invalid_type(client, seeded_data):
    token = seeded_data["token"]
    resp = await client.post(
        "/v1/jobs",
        headers={"X-API-Key": token, "X-External-User-Id": "user1"},
        json={"job_type": "nonexistent", "input": {}},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_JOB_TYPE"
