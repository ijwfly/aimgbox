from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import httpx
import structlog

from aimg.db.models import Integration, Job, JobType, WebhookDelivery
from aimg.db.repos.webhook_deliveries import WebhookDeliveryRepo

logger = structlog.get_logger()

RETRY_BACKOFFS = [10, 60, 300]  # seconds
MAX_ATTEMPTS = 3


def sign_payload(payload_bytes: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def build_webhook_payload(job: Job, job_type: JobType) -> dict:
    event = f"job.{job.status}"
    payload: dict = {
        "event": event,
        "job_id": str(job.id),
        "status": job.status,
        "job_type": job_type.slug,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
    if job.status == "failed" and job.error_code:
        payload["error"] = {
            "code": job.error_code,
            "message": job.error_message,
        }
    return payload


async def deliver_webhook(
    delivery: WebhookDelivery,
    webhook_url: str,
    webhook_secret: str,
) -> tuple[bool, int | None, str | None]:
    payload_bytes = json.dumps(delivery.payload, default=str).encode()
    signature = sign_payload(payload_bytes, webhook_secret)
    headers = {
        "Content-Type": "application/json",
        "X-AIMG-Signature": signature,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                webhook_url,
                content=payload_bytes,
                headers=headers,
            )
        success = 200 <= resp.status_code < 300
        return success, resp.status_code, None if success else resp.text[:500]
    except Exception as exc:
        return False, None, str(exc)[:500]


def calculate_next_retry(attempt_number: int) -> datetime | None:
    idx = attempt_number - 1
    if idx >= len(RETRY_BACKOFFS):
        return None  # exhausted
    return datetime.now(UTC) + timedelta(seconds=RETRY_BACKOFFS[idx])


async def attempt_delivery(
    delivery: WebhookDelivery,
    integration: Integration,
    repo: WebhookDeliveryRepo,
) -> bool:
    if not integration.webhook_url or not integration.webhook_secret:
        await repo.update_delivery(
            delivery.id, status="failed", attempts=delivery.attempts,
            last_error="No webhook URL or secret configured",
        )
        return False

    success, status_code, error = await deliver_webhook(
        delivery, integration.webhook_url, integration.webhook_secret
    )
    new_attempts = delivery.attempts + 1

    if success:
        await repo.update_delivery(
            delivery.id, status="delivered", attempts=new_attempts,
            last_status_code=status_code,
        )
        logger.info("webhook_delivered", delivery_id=str(delivery.id))
        return True

    next_retry = calculate_next_retry(new_attempts)
    new_status = "pending" if next_retry else "failed"
    await repo.update_delivery(
        delivery.id, status=new_status, attempts=new_attempts,
        last_status_code=status_code, last_error=error,
        next_retry_at=next_retry,
    )
    logger.warning(
        "webhook_delivery_failed",
        delivery_id=str(delivery.id),
        attempt=new_attempts,
        status_code=status_code,
        will_retry=next_retry is not None,
    )
    return False
