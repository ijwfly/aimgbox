import hashlib
import hmac
from datetime import UTC, datetime
from uuid import uuid4

from aimg.db.models import Job, JobType
from aimg.services.webhooks import (
    build_webhook_payload,
    calculate_next_retry,
    sign_payload,
)


def test_sign_payload():
    payload = b'{"event":"job.succeeded"}'
    secret = "test-secret"
    result = sign_payload(payload, secret)

    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert result == f"sha256={expected}"


def _make_job(status="succeeded", error_code=None, error_message=None):
    now = datetime.now(UTC)
    return Job(
        id=uuid4(),
        integration_id=uuid4(),
        user_id=uuid4(),
        job_type_id=uuid4(),
        status=status,
        input_data={},
        output_data={} if status == "succeeded" else None,
        credit_charged=1,
        error_code=error_code,
        error_message=error_message,
        attempts=1,
        language="en",
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )


def _make_job_type():
    now = datetime.now(UTC)
    return JobType(
        id=uuid4(),
        slug="remove_bg",
        name="Remove Background",
        input_schema={},
        output_schema={},
        credit_cost=1,
        timeout_seconds=300,
        status="active",
        created_at=now,
        updated_at=now,
    )


def test_build_webhook_payload_succeeded():
    job = _make_job(status="succeeded")
    job_type = _make_job_type()
    payload = build_webhook_payload(job, job_type)

    assert payload["event"] == "job.succeeded"
    assert payload["job_id"] == str(job.id)
    assert payload["status"] == "succeeded"
    assert payload["job_type"] == "remove_bg"
    assert "created_at" in payload
    assert "completed_at" in payload
    assert "error" not in payload


def test_build_webhook_payload_failed():
    job = _make_job(
        status="failed",
        error_code="PROVIDER_ERROR",
        error_message="All providers failed",
    )
    job_type = _make_job_type()
    payload = build_webhook_payload(job, job_type)

    assert payload["event"] == "job.failed"
    assert payload["error"]["code"] == "PROVIDER_ERROR"
    assert payload["error"]["message"] == "All providers failed"


def test_calculate_next_retry():
    r1 = calculate_next_retry(1)
    assert r1 is not None

    r2 = calculate_next_retry(2)
    assert r2 is not None
    assert r2 > r1  # second retry is later

    r3 = calculate_next_retry(3)
    assert r3 is not None

    # After max attempts, should return None
    r4 = calculate_next_retry(4)
    assert r4 is None
