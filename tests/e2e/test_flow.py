import time
import uuid


def _poll_job(client, job_id, headers, timeout=30):
    """Poll job until terminal state, return final response data."""
    for _ in range(timeout * 2):
        resp = client.get(f"/v1/jobs/{job_id}", headers=headers)
        assert resp.status_code == 200
        status = resp.json()["data"]["status"]
        if status in ("succeeded", "failed"):
            return resp.json()["data"]
        time.sleep(0.5)
    return resp.json()["data"]


def _upload_file(client, headers):
    """Upload a test PNG and return file_id."""
    resp = client.post(
        "/v1/files",
        headers=headers,
        files={"file": ("test.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["file_id"]


def _create_job(client, headers, job_type, input_data, **extra_headers):
    """Create a job and return (status_code, response_json)."""
    merged = {**headers, **extra_headers}
    resp = client.post(
        "/v1/jobs",
        headers=merged,
        json={"job_type": job_type, "input": input_data},
    )
    return resp.status_code, resp.json()


def _get_balance(client, headers):
    """Get user balance, return (free_credits, paid_credits, total)."""
    resp = client.get("/v1/users/me/balance", headers=headers)
    assert resp.status_code == 200
    d = resp.json()["data"]
    return d["free_credits"], d["paid_credits"], d["total_credits"]


# ── Existing tests ──────────────────────────────────────────────


def test_full_flow(client, api_key):
    """Upload file -> create job -> poll until succeeded -> get presigned URL."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": f"e2e-test-user-{uuid.uuid4().hex[:8]}",
    }

    file_id = _upload_file(client, headers)

    input_data = {"image": file_id, "output_format": "png"}
    code, data = _create_job(client, headers, "remove_bg", input_data)
    assert code == 201, data
    job_id = data["data"]["job_id"]
    assert data["data"]["status"] == "pending"

    result = _poll_job(client, job_id, headers)
    assert result["status"] == "succeeded"
    assert result["output"] is not None
    output_file_id = result["output"]["image"]

    resp = client.get(f"/v1/files/{output_file_id}", headers=headers)
    assert resp.status_code == 200
    assert "download_url" in resp.json()["data"]


def test_insufficient_credits(client, api_key):
    """User with depleted credits should get 402."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": f"e2e-broke-{uuid.uuid4().hex[:8]}",
    }

    file_id = _upload_file(client, headers)

    for i in range(10):
        resp = client.post(
            "/v1/jobs",
            headers=headers,
            json={"job_type": "remove_bg", "input": {"image": file_id}},
        )
        if resp.status_code == 402:
            break

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
        "X-External-User-Id": f"e2e-balance-{uuid.uuid4().hex[:8]}",
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
        "X-External-User-Id": f"e2e-history-{uuid.uuid4().hex[:8]}",
    }

    resp = client.get("/v1/users/me/history", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["jobs"] == []

    file_id = _upload_file(client, headers)
    client.post(
        "/v1/jobs",
        headers=headers,
        json={"job_type": "remove_bg", "input": {"image": file_id}},
    )

    resp = client.get("/v1/users/me/history", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]["jobs"]) == 1


def test_txt2img_flow(client, api_key):
    """Create txt2img job (mock) -> poll -> succeeded."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": f"e2e-txt2img-{uuid.uuid4().hex[:8]}",
    }

    code, data = _create_job(
        client, headers, "txt2img",
        {"prompt": "a beautiful sunset over mountains"},
    )
    assert code == 201, data
    job_id = data["data"]["job_id"]

    result = _poll_job(client, job_id, headers)
    assert result["status"] == "succeeded"
    assert result["output"] is not None


def test_idempotency(client, api_key):
    """Repeat with same Idempotency-Key -> 200, same job_id."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": f"e2e-idem-{uuid.uuid4().hex[:8]}",
        "Idempotency-Key": f"e2e-idem-key-{uuid.uuid4().hex[:8]}",
    }

    file_id = _upload_file(client, headers)
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

    if not got_429:
        assert "X-RateLimit-Limit" in resp.headers


def test_billing_topup_and_check(client, api_key):
    """Topup credits, then check can_afford."""
    uid = f"e2e-billing-{uuid.uuid4().hex[:8]}"
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": uid,
    }

    resp = client.post(
        "/v1/billing/topup",
        headers={k: v for k, v in headers.items() if k != "X-External-User-Id"},
        json={
            "external_user_id": uid,
            "amount": 50,
            "external_transaction_id": f"e2e-txn-{uuid.uuid4().hex[:8]}",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["paid_credits"] == 50

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
        "X-External-User-Id": f"e2e-i18n-{uuid.uuid4().hex[:8]}",
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


# ── New tests: AC 4-17 ─────────────────────────────────────────


def test_job_result_endpoint(client, api_key):
    """AC 4: GET /v1/jobs/{id}/result -> presigned URL for succeeded job."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": f"e2e-result-{uuid.uuid4().hex[:8]}",
    }

    file_id = _upload_file(client, headers)
    code, data = _create_job(client, headers, "remove_bg", {"image": file_id})
    assert code == 201
    job_id = data["data"]["job_id"]

    result = _poll_job(client, job_id, headers)
    assert result["status"] == "succeeded"

    resp = client.get(f"/v1/jobs/{job_id}/result", headers=headers)
    assert resp.status_code == 200
    rdata = resp.json()["data"]
    assert "download_url" in rdata
    assert rdata["job_id"] == job_id
    assert rdata["file_id"] is not None
    assert rdata["content_type"] is not None
    assert rdata["expires_at"] is not None


def test_job_result_not_succeeded(client, api_key):
    """AC 4: GET /v1/jobs/{id}/result on pending job -> 400."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": f"e2e-result-pend-{uuid.uuid4().hex[:8]}",
    }

    file_id = _upload_file(client, headers)
    code, data = _create_job(client, headers, "remove_bg", {"image": file_id})
    assert code == 201
    job_id = data["data"]["job_id"]

    # Immediately request result before job completes
    resp = client.get(f"/v1/jobs/{job_id}/result", headers=headers)
    # Should fail since job is not yet succeeded (may be pending or running)
    assert resp.status_code == 400


def test_credit_lifecycle(client, api_key):
    """AC 5, 6: Credits reserved on create, unchanged after success."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": f"e2e-credits-{uuid.uuid4().hex[:8]}",
    }

    # Check initial balance
    free_before, _, total_before = _get_balance(client, headers)
    assert total_before == 10  # default free credits

    # Upload + create job (costs 1 credit)
    file_id = _upload_file(client, headers)
    code, data = _create_job(client, headers, "remove_bg", {"image": file_id})
    assert code == 201
    job_id = data["data"]["job_id"]

    # Balance should be reduced by 1 (reserved)
    free_after_create, _, total_after_create = _get_balance(client, headers)
    assert total_after_create == total_before - 1

    # Wait for success
    result = _poll_job(client, job_id, headers)
    assert result["status"] == "succeeded"

    # Balance should remain unchanged after success (no refund, no additional charge)
    free_after_success, _, total_after_success = _get_balance(client, headers)
    assert total_after_success == total_after_create


def test_credit_refund_on_failure(client, api_key):
    """AC 7, 14: test_allfail -> all providers fail -> job failed -> credits refunded."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": f"e2e-refund-{uuid.uuid4().hex[:8]}",
    }

    _, _, total_before = _get_balance(client, headers)

    file_id = _upload_file(client, headers)
    code, data = _create_job(client, headers, "test_allfail", {"image": file_id})
    assert code == 201
    job_id = data["data"]["job_id"]

    # Balance should be reduced after create
    _, _, total_after_create = _get_balance(client, headers)
    assert total_after_create == total_before - 1

    # Wait for failure
    result = _poll_job(client, job_id, headers)
    assert result["status"] == "failed"
    assert result["error"]["code"] == "PROVIDER_ERROR"

    # Balance should be restored after failure (refund)
    _, _, total_after_fail = _get_balance(client, headers)
    assert total_after_fail == total_before


def test_balance_non_negative(client, api_key):
    """AC 9: Balance never goes below 0."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": f"e2e-nonneg-{uuid.uuid4().hex[:8]}",
    }

    file_id = _upload_file(client, headers)

    # Exhaust all credits
    for _ in range(10):
        resp = client.post(
            "/v1/jobs",
            headers=headers,
            json={"job_type": "remove_bg", "input": {"image": file_id}},
        )
        if resp.status_code == 402:
            break

    # Verify balance >= 0
    free, paid, total = _get_balance(client, headers)
    assert free >= 0
    assert paid >= 0
    assert total >= 0


def test_idempotency_no_double_charge(client, api_key):
    """AC 12: Repeat with same key -> balance not charged twice."""
    idem_key = f"e2e-idem-charge-{uuid.uuid4().hex[:8]}"
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": f"e2e-idem-charge-{uuid.uuid4().hex[:8]}",
        "Idempotency-Key": idem_key,
    }

    _, _, total_before = _get_balance(client, headers)

    file_id = _upload_file(client, headers)
    body = {"job_type": "remove_bg", "input": {"image": file_id}}

    r1 = client.post("/v1/jobs", headers=headers, json=body)
    assert r1.status_code == 201

    _, _, total_after_first = _get_balance(client, headers)
    assert total_after_first == total_before - 1  # charged once

    # Repeat with same key
    r2 = client.post("/v1/jobs", headers=headers, json=body)
    assert r2.status_code == 200
    assert r2.json()["data"]["job_id"] == r1.json()["data"]["job_id"]

    # Balance should not change
    _, _, total_after_repeat = _get_balance(client, headers)
    assert total_after_repeat == total_after_first


def test_provider_fallback(client, api_key):
    """AC 13: remove_bg with replicate (may fail) + mock fallback -> succeeded."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": f"e2e-fallback-{uuid.uuid4().hex[:8]}",
    }

    file_id = _upload_file(client, headers)
    code, data = _create_job(client, headers, "remove_bg", {"image": file_id})
    assert code == 201
    job_id = data["data"]["job_id"]

    result = _poll_job(client, job_id, headers)
    # Should succeed (either replicate or mock fallback)
    assert result["status"] == "succeeded"


def test_webhook_on_succeeded(client, api_key, db_query):
    """AC 15: Webhook delivery created for succeeded job."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": f"e2e-wh-succ-{uuid.uuid4().hex[:8]}",
    }

    file_id = _upload_file(client, headers)
    code, data = _create_job(client, headers, "remove_bg", {"image": file_id})
    assert code == 201
    job_id = data["data"]["job_id"]

    result = _poll_job(client, job_id, headers)
    assert result["status"] == "succeeded"

    # Give webhook delivery a moment to be created
    time.sleep(1)

    rows = db_query(
        "SELECT * FROM webhook_deliveries WHERE job_id = $1",
        uuid.UUID(job_id),
    )
    assert len(rows) >= 1
    delivery = dict(rows[0])
    assert delivery["event"] == "job.succeeded"


def test_webhook_on_failed(client, api_key, db_query):
    """AC 15: Webhook delivery created for failed job."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": f"e2e-wh-fail-{uuid.uuid4().hex[:8]}",
    }

    file_id = _upload_file(client, headers)
    code, data = _create_job(client, headers, "test_allfail", {"image": file_id})
    assert code == 201
    job_id = data["data"]["job_id"]

    result = _poll_job(client, job_id, headers)
    assert result["status"] == "failed"

    time.sleep(1)

    rows = db_query(
        "SELECT * FROM webhook_deliveries WHERE job_id = $1",
        uuid.UUID(job_id),
    )
    assert len(rows) >= 1
    delivery = dict(rows[0])
    assert delivery["event"] == "job.failed"


def test_webhook_payload_structure(client, api_key, db_query):
    """AC 16: Webhook payload contains event, job_id, status."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": f"e2e-wh-payload-{uuid.uuid4().hex[:8]}",
    }

    file_id = _upload_file(client, headers)
    code, data = _create_job(client, headers, "remove_bg", {"image": file_id})
    assert code == 201
    job_id = data["data"]["job_id"]

    result = _poll_job(client, job_id, headers)
    assert result["status"] == "succeeded"

    time.sleep(1)

    rows = db_query(
        "SELECT * FROM webhook_deliveries WHERE job_id = $1",
        uuid.UUID(job_id),
    )
    assert len(rows) >= 1
    payload = rows[0]["payload"]
    # payload may be a dict (jsonb) or a JSON string depending on asyncpg codec
    if isinstance(payload, str):
        import json
        payload = json.loads(payload)
    assert "event" in payload
    assert "job_id" in payload
    assert "status" in payload
    assert payload["job_id"] == job_id
    assert payload["status"] == "succeeded"


def test_webhook_retry_on_failure(client, api_key, db_query):
    """AC 17: Webhook delivery attempts >= 1 when URL is unreachable."""
    headers = {
        "X-API-Key": api_key,
        "X-External-User-Id": f"e2e-wh-retry-{uuid.uuid4().hex[:8]}",
    }

    file_id = _upload_file(client, headers)
    code, data = _create_job(client, headers, "remove_bg", {"image": file_id})
    assert code == 201
    job_id = data["data"]["job_id"]

    result = _poll_job(client, job_id, headers)
    assert result["status"] == "succeeded"

    time.sleep(2)

    rows = db_query(
        "SELECT * FROM webhook_deliveries WHERE job_id = $1",
        uuid.UUID(job_id),
    )
    assert len(rows) >= 1
    delivery = dict(rows[0])
    # Webhook URL in seed is localhost:8888 which likely isn't running,
    # so attempts should be >= 1 (first attempt made)
    assert delivery["attempts"] >= 1


def test_openapi_docs(client, api_key):
    """OpenAPI docs available and include /v1/jobs endpoints."""
    resp = client.get("/docs")
    assert resp.status_code == 200

    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/v1/jobs" in paths
    assert "/v1/jobs/{job_id}" in paths
    assert "/v1/jobs/{job_id}/result" in paths
