async def test_upload_file(client, seeded_data):
    token = seeded_data["token"]
    resp = await client.post(
        "/v1/files",
        headers={
            "X-API-Key": token,
            "X-External-User-Id": "user1",
        },
        files={"file": ("photo.png", b"fake-png-data", "image/png")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["original_filename"] == "photo.png"
    assert body["data"]["content_type"] == "image/png"
    assert body["data"]["size_bytes"] == len(b"fake-png-data")
    assert "file_id" in body["data"]


async def test_get_file_presigned_url(client, seeded_data):
    token = seeded_data["token"]

    # Upload first
    upload_resp = await client.post(
        "/v1/files",
        headers={
            "X-API-Key": token,
            "X-External-User-Id": "user1",
        },
        files={"file": ("test.jpg", b"jpeg-data", "image/jpeg")},
    )
    file_id = upload_resp.json()["data"]["file_id"]

    # Get presigned URL
    resp = await client.get(
        f"/v1/files/{file_id}",
        headers={
            "X-API-Key": token,
            "X-External-User-Id": "user1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "download_url" in body["data"]
    assert body["data"]["file_id"] == file_id


async def test_get_nonexistent_file(client, seeded_data):
    resp = await client.get(
        "/v1/files/00000000-0000-0000-0000-000000000000",
        headers={
            "X-API-Key": seeded_data["token"],
            "X-External-User-Id": "user1",
        },
    )
    assert resp.status_code == 404
