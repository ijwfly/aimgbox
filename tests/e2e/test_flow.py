import time


def test_full_flow(client, api_key):
    """Upload file → create job → poll until succeeded → get presigned URL."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": "e2e-test-user",
    }

    # 1. Upload file
    resp = client.post(
        "/v1/files",
        headers=headers,
        files={"file": ("test.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
    )
    assert resp.status_code == 201, resp.text
    file_id = resp.json()["data"]["file_id"]

    # 2. Create job
    resp = client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "job_type": "remove_bg",
            "input": {"image": file_id, "output_format": "png"},
        },
    )
    assert resp.status_code == 201, resp.text
    job_id = resp.json()["data"]["job_id"]
    assert resp.json()["data"]["status"] == "pending"

    # 3. Poll until succeeded (or failed)
    for _ in range(30):
        resp = client.get(f"/v1/jobs/{job_id}", headers=headers)
        assert resp.status_code == 200
        status = resp.json()["data"]["status"]
        if status in ("succeeded", "failed"):
            break
        time.sleep(0.5)

    assert status == "succeeded", f"Job ended with status={status}"
    job_data = resp.json()["data"]
    assert job_data["output"] is not None
    output_file_id = job_data["output"]["image"]

    # 4. Get presigned URL for output file
    resp = client.get(f"/v1/files/{output_file_id}", headers=headers)
    assert resp.status_code == 200
    assert "download_url" in resp.json()["data"]


def test_insufficient_credits(client, api_key):
    """User with depleted credits should get 402."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": "e2e-broke-user-unique",
    }

    # This user gets 10 free credits by default.
    # Create 10 jobs to exhaust credits (each costs 1 by default).
    file_resp = client.post(
        "/v1/files",
        headers=headers,
        files={"file": ("test.png", b"data", "image/png")},
    )
    file_id = file_resp.json()["data"]["file_id"]

    for i in range(10):
        resp = client.post(
            "/v1/jobs",
            headers=headers,
            json={"job_type": "remove_bg", "input": {"image": file_id}},
        )
        if resp.status_code == 402:
            break  # Credits exhausted early

    # 11th job should fail
    resp = client.post(
        "/v1/jobs",
        headers=headers,
        json={"job_type": "remove_bg", "input": {"image": file_id}},
    )
    assert resp.status_code == 402
    assert resp.json()["error"]["code"] == "INSUFFICIENT_CREDITS"
