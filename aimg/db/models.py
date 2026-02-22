from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class Partner(BaseModel):
    id: UUID
    name: str
    status: str
    created_at: datetime
    updated_at: datetime


class Integration(BaseModel):
    id: UUID
    partner_id: UUID
    name: str
    status: str
    webhook_url: str | None = None
    webhook_secret: str | None = None
    rate_limit_rpm: int
    default_free_credits: int
    created_at: datetime
    updated_at: datetime


class ApiKey(BaseModel):
    id: UUID
    integration_id: UUID
    key_hash: str
    label: str | None = None
    is_revoked: bool
    created_at: datetime
    revoked_at: datetime | None = None


class Provider(BaseModel):
    id: UUID
    slug: str
    name: str
    adapter_class: str
    base_url: str | None = None
    api_key_encrypted: str
    config: dict
    status: str
    created_at: datetime
    updated_at: datetime


class JobType(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str | None = None
    input_schema: dict
    output_schema: dict
    credit_cost: int
    timeout_seconds: int
    status: str
    created_at: datetime
    updated_at: datetime


class JobTypeProvider(BaseModel):
    job_type_id: UUID
    provider_id: UUID
    priority: int
    config_override: dict


class User(BaseModel):
    id: UUID
    integration_id: UUID
    external_user_id: str
    free_credits: int
    paid_credits: int
    created_at: datetime
    updated_at: datetime


class File(BaseModel):
    id: UUID
    integration_id: UUID
    user_id: UUID | None = None
    s3_bucket: str
    s3_key: str
    original_filename: str | None = None
    content_type: str
    size_bytes: int
    purpose: str
    created_at: datetime


class Job(BaseModel):
    id: UUID
    integration_id: UUID
    user_id: UUID
    job_type_id: UUID
    status: str
    input_data: dict
    output_data: dict | None = None
    provider_id: UUID | None = None
    credit_charged: int
    error_code: str | None = None
    error_message: str | None = None
    provider_job_id: str | None = None
    attempts: int
    language: str
    idempotency_key: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class JobAttempt(BaseModel):
    id: UUID
    job_id: UUID
    provider_id: UUID
    attempt_number: int
    status: str
    error_code: str | None = None
    error_message: str | None = None
    duration_ms: int | None = None
    started_at: datetime
    completed_at: datetime | None = None


class CreditTransaction(BaseModel):
    id: UUID
    user_id: UUID
    amount: int
    credit_type: str
    reason: str
    job_id: UUID | None = None
    admin_user_id: UUID | None = None
    comment: str | None = None
    external_transaction_id: str | None = None
    balance_after: int
    created_at: datetime


class WebhookDelivery(BaseModel):
    id: UUID
    integration_id: UUID
    job_id: UUID
    event: str
    payload: dict
    status: str
    attempts: int
    last_status_code: int | None = None
    last_error: str | None = None
    next_retry_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
