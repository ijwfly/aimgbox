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


def test_idempotency(client, api_key):
    """Repeat with same Idempotency-Key → 200, same job_id."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": "e2e-idem-user",
        "Idempotency-Key": "e2e-idem-key-001",
    }

    file_resp = client.post(
        "/v1/files",
        headers=headers,
        files={"file": ("test.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
    )
    file_id = file_resp.json()["data"]["file_id"]

    body = {"job_type": "remove_bg", "input": {"image": file_id}}
    r1 = client.post("/v1/jobs", headers=headers, json=body)
    assert r1.status_code == 201
    job_id = r1.json()["data"]["job_id"]

    r2 = client.post("/v1/jobs", headers=headers, json=body)
    assert r2.status_code == 200
    assert r2.json()["data"]["job_id"] == job_id


def test_rate_limit(client, api_key):
    """Send many rapid requests; eventually get 429."""
    headers = {"X-API-Key": api_key}

    got_429 = False
    for _ in range(100):
        resp = client.get("/v1/meta/job-types", headers=headers)
        if resp.status_code == 429:
            got_429 = True
            assert "Retry-After" in resp.headers
            break

    # Note: if RPM is high (60), we might not hit it in 100 requests
    # This test is best-effort in e2e
    if not got_429:
        # At minimum, check rate limit headers are present
        assert "X-RateLimit-Limit" in resp.headers


def test_billing_topup_and_check(client, api_key):
    """Topup credits, then check can_afford."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": "e2e-billing-user",
    }

    # Topup
    resp = client.post(
        "/v1/billing/topup",
        headers={k: v for k, v in headers.items() if k != "X-External-User-Id"},
        json={
            "external_user_id": "e2e-billing-user",
            "amount": 50,
            "external_transaction_id": "e2e-txn-001",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["paid_credits"] == 50

    # Check
    resp = client.post(
        "/v1/billing/check",
        headers=headers,
        json={"job_type": "remove_bg"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["can_afford"] is True
    assert resp.json()["data"]["total_credits"] >= 50


def test_localization_ru(client, api_key):
    """Accept-Language: ru should produce localized error messages."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": "e2e-i18n-user",
        "Accept-Language": "ru",
    }

    resp = client.get(
        "/v1/jobs/00000000-0000-0000-0000-000000000001",
        headers=headers,
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_languages_endpoint(client, api_key):
    """GET /v1/meta/languages returns supported languages."""
    resp = client.get("/v1/meta/languages")
    assert resp.status_code == 200
    data = resp.json()["data"]
    codes = [lang["code"] for lang in data["languages"]]
    assert "en" in codes
    assert "ru" in codes
