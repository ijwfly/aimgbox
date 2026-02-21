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


def test_meta_job_types(client, api_key):
    """Both remove_bg and txt2img should be listed."""
    headers = {"X-API-Key": api_key}
    resp = client.get("/v1/meta/job-types", headers=headers)
    assert resp.status_code == 200
    slugs = [jt["slug"] for jt in resp.json()["data"]["job_types"]]
    assert "remove_bg" in slugs
    assert "txt2img" in slugs


def test_user_balance(client, api_key):
    """New user should have default free credits."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": "e2e-balance-user",
    }
    resp = client.get("/v1/users/me/balance", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["free_credits"] == 10
    assert data["total_credits"] == 10


def test_user_history(client, api_key):
    """Job should appear in history after creation."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": "e2e-history-user",
    }

    # Initially empty
    resp = client.get("/v1/users/me/history", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["jobs"] == []

    # Upload + create job
    file_resp = client.post(
        "/v1/files",
        headers=headers,
        files={"file": ("test.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
    )
    file_id = file_resp.json()["data"]["file_id"]

    client.post(
        "/v1/jobs",
        headers=headers,
        json={"job_type": "remove_bg", "input": {"image": file_id}},
    )

    resp = client.get("/v1/users/me/history", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]["jobs"]) == 1


def test_txt2img_flow(client, api_key):
    """Create txt2img job (mock) → poll → succeeded."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": "e2e-txt2img-user",
    }

    resp = client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "job_type": "txt2img",
            "input": {"prompt": "a beautiful sunset over mountains"},
        },
    )
    assert resp.status_code == 201, resp.text
    job_id = resp.json()["data"]["job_id"]

    for _ in range(30):
        resp = client.get(f"/v1/jobs/{job_id}", headers=headers)
        assert resp.status_code == 200
        status = resp.json()["data"]["status"]
        if status in ("succeeded", "failed"):
            break
        time.sleep(0.5)

    assert status == "succeeded", f"Job ended with status={status}"
    assert resp.json()["data"]["output"] is not None
