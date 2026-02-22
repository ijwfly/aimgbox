# AIMG — AI Image Processing B2B2C API

## Overview
B2B2C API for AI image processing. Partners integrate via REST API, submit image processing jobs (background removal, text-to-image, etc.), and receive results. Built with FastAPI + asyncpg + Redis + S3.

## Stack
- **API**: FastAPI, asyncpg (no ORM), redis, aiobotocore (S3), pyjwt, python-multipart
- **Worker**: asyncio process reading from Redis queue (BRPOP)
- **Admin**: Starlette + Jinja2 + htmx + Pico CSS
- **DB**: PostgreSQL 16, migrations via Alembic
- **Queue/Cache**: Redis 7
- **Storage**: S3 (MinIO for dev)
- **Config**: pydantic-settings with `AIMG_` prefix
- **Logging**: structlog (JSON)
- **Python**: 3.12, managed with uv

## Project Structure
```
aimg/
├── __init__.py          # __version__
├── __main__.py          # CLI: api|worker|admin|seed|sync-job-types|create-admin|reconcile-balances
├── common/
│   ├── settings.py      # Settings(BaseSettings) — all env vars
│   ├── logging.py       # structlog config, request_id ContextVar
│   ├── connections.py   # create_db_pool, create_redis_client, create_s3_client
│   ├── encryption.py    # encrypt_value, decrypt_value (Fernet)
│   ├── health.py        # check_database, check_redis, check_storage
│   ├── i18n.py          # translate_error(), load locales
│   └── pagination.py    # cursor-based pagination helpers
├── api/
│   ├── app.py           # create_app(settings) factory with lifespan
│   ├── envelope.py      # ApiResponse[T], ErrorDetail
│   ├── errors.py        # AppError hierarchy + exception handler
│   ├── dependencies.py  # FastAPI Depends: get_current_integration/user/s3_client/settings
│   ├── middleware.py     # RequestIdMiddleware, language + rate limit headers
│   └── routes/
│       ├── health.py    # GET /health
│       ├── files.py     # POST/GET /v1/files
│       ├── jobs.py      # POST/GET /v1/jobs, GET /v1/jobs/{id}/result
│       ├── users.py     # GET /v1/users/me/balance, /v1/users/me/history
│       ├── billing.py   # POST /v1/billing/topup, /v1/billing/check
│       └── meta.py      # GET /v1/meta/job-types, /v1/meta/languages
├── worker/
│   └── main.py          # run_worker() — BRPOP loop, process_job, recovery janitor, webhook retry
├── admin/
│   ├── app.py           # create_admin_app(settings) factory with Starlette routes
│   ├── auth.py          # hash_password, verify_password, create_session, destroy_session
│   ├── middleware.py     # AdminSessionMiddleware (Redis sessions + HMAC cookies)
│   ├── decorators.py    # require_auth, require_role(*roles)
│   ├── audit.py         # log_action(request, action, entity_type, entity_id, details)
│   ├── pagination.py    # get_page_info()
│   ├── csv_export.py    # export_jobs_csv()
│   ├── templates/       # Jinja2 templates (Pico CSS + htmx)
│   └── routes/
│       ├── auth.py      # login/logout
│       ├── dashboard.py # dashboard with stats
│       ├── partners.py  # CRUD partners
│       ├── integrations.py # CRUD integrations
│       ├── api_keys.py  # generate/revoke API keys
│       ├── users.py     # list/detail/credit adjustment
│       ├── jobs.py      # list/detail/CSV export
│       ├── job_types.py # list/detail/update/provider management
│       ├── providers.py # CRUD providers
│       └── audit.py     # audit log list
├── db/
│   ├── models.py        # Pydantic models for all tables
│   └── repos/
│       ├── __init__.py          # BaseRepo with _fetchrow/_fetch/_execute
│       ├── partners.py          # PartnerRepo
│       ├── integrations.py      # IntegrationRepo
│       ├── api_keys.py          # ApiKeyRepo
│       ├── users.py             # UserRepo (get_or_create, update_credits)
│       ├── files.py             # FileRepo
│       ├── jobs.py              # JobRepo
│       ├── job_types.py         # JobTypeRepo (upsert, get_providers)
│       ├── job_attempts.py      # JobAttemptRepo
│       ├── providers.py         # ProviderRepo
│       ├── credit_transactions.py # CreditTransactionRepo
│       ├── webhook_deliveries.py  # WebhookDeliveryRepo
│       ├── admin_users.py       # AdminUserRepo
│       └── audit_log.py         # AuditLogRepo
├── jobs/
│   ├── fields.py        # InputFile, OutputFile, FileConstraints
│   ├── registry.py      # JobRegistry, @job_handler decorator, discover_handlers
│   ├── context.py       # JobContext[TInput, TOutput]
│   └── handlers/
│       ├── remove_bg.py     # RemoveBgInput/Output, handle_remove_bg
│       ├── txt2img.py       # Txt2ImgInput/Output, handle_txt2img
│       └── test_allfail.py  # Test handler (all providers fail)
├── services/
│   ├── auth.py          # generate/verify/hash JWT API keys
│   ├── billing.py       # reserve/refund credits, calculate_credit_split
│   ├── rate_limit.py    # check_integration_rpm, check_user_jobs_per_hour (sliding window)
│   └── webhooks.py      # sign_payload, build_webhook_payload, deliver_webhook, attempt_delivery
├── providers/
│   ├── base.py          # ProviderAdapter ABC, ProviderResult, ProviderError, AllProvidersFailedError
│   ├── mock.py          # MockProvider (echo or 1x1 PNG)
│   ├── replicate.py     # ReplicateAdapter (Replicate API)
│   └── failing_mock.py  # FailingMockProvider (always fails, for testing)
└── scripts/
    ├── seed.py          # Create test partner+integration+key+providers+job_types+admin
    ├── sync_job_types.py # Sync handlers → job_types table
    ├── create_admin.py  # Create admin user CLI
    └── reconcile.py     # Check/fix credit balance mismatches
```

## Commands
```bash
uv sync                              # Install dependencies
uv run pytest tests/unit/            # Unit tests (no infra needed)
uv run pytest tests/functional/      # Functional tests (needs postgres, redis, minio)
uv run pytest tests/e2e/             # E2E tests (needs full docker-compose up + seed)
uv run python -m aimg api            # Start API server
uv run python -m aimg worker         # Start worker
uv run python -m aimg admin          # Start admin panel
uv run python -m aimg seed           # Seed DB with test data, prints JWT
uv run python -m aimg sync-job-types # Sync handler registry → DB
uv run python -m aimg create-admin --username X --password Y --role admin  # Create admin user
uv run python -m aimg reconcile-balances  # Check/fix credit balance mismatches
uv run alembic upgrade head          # Run migrations
docker-compose up -d                 # Start all services
uv run ruff check .                  # Lint
```

## Key Patterns
- **No ORM**: asyncpg with raw SQL, thin repository layer via BaseRepo
- **App factory**: `create_app(settings)` — testable with custom settings
- **Lifespan**: connections created at startup, closed at shutdown
- **Request ID**: UUID via middleware → ContextVar → structlog
- **Health endpoint**: plain JSON (not wrapped in envelope), checks all deps
- **Envelope**: `{request_id, success, data, error}` for all v1/ endpoints (not /health)
- **API keys as JWT**: HS256, revocation cache in Redis set `aimg:revoked_keys`
- **Auth dependencies**: `get_current_integration()` (decode JWT → check revocation → load integration), `get_current_user()` (get_or_create by external_user_id)
- **Repos accept `conn=None`**: if conn passed, use it (for transactions); else acquire from pool
- **Billing**: two-phase — reserve on job create, confirm on success, refund on failure
- **Job handlers**: `@job_handler(slug, name, desc)` decorator, `discover_handlers()` at startup
- **Worker**: BRPOP from `aimg:jobs:queue`, resolve InputFile from S3, call handler, upload OutputFile
- **Worker recovery**: orphan re-enqueue on startup, janitor loop for stuck running jobs
- **Rate limiting**: sliding window via Redis sorted sets, per-integration RPM + per-user jobs/hour
- **Idempotency**: `Idempotency-Key` header → Redis cache (24h TTL) + DB unique index
- **Webhooks**: HMAC-SHA256 signed, retry with backoff (10s, 60s, 300s), max 3 attempts
- **i18n**: locales/en.json + locales/ru.json, `translate_error()`, `Accept-Language` header or `?lang=` param
- **Admin auth**: `AdminSessionMiddleware` with Redis sessions + HMAC cookies
- **Admin RBAC**: `require_auth` + `require_role(*roles)` decorators; roles: super_admin/admin/viewer
- **Admin audit**: `log_action()` → audit_log table for all mutations
- **Admin templates**: Pico CSS + htmx CDN, `base.html` → section templates, `_rows.html` partials for htmx

## Environment Variables
All prefixed with `AIMG_`. Required (no default): `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `JWT_SECRET`, `ENCRYPTION_KEY`, `ADMIN_SESSION_SECRET`.
See `aimg/common/settings.py` for full list with defaults.
