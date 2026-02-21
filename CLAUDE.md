# AIMG — AI Image Processing B2B2C API

## Overview
B2B2C API for AI image processing. Partners integrate via REST API, submit image processing jobs (background removal, text-to-image, etc.), and receive results. Built with FastAPI + asyncpg + Redis + S3.

## Stack
- **API**: FastAPI, asyncpg (no ORM), redis, aiobotocore (S3), pyjwt, python-multipart
- **Worker**: asyncio process reading from Redis queue (BRPOP)
- **Admin**: Starlette + Jinja2 + htmx
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
├── __main__.py          # CLI: api|worker|admin|seed|sync-job-types
├── common/
│   ├── settings.py      # Settings(BaseSettings) — all env vars
│   ├── logging.py       # structlog config, request_id ContextVar
│   ├── connections.py   # create_db_pool, create_redis_client, create_s3_client
│   └── health.py        # check_database, check_redis, check_storage
├── api/
│   ├── app.py           # create_app(settings) factory with lifespan
│   ├── envelope.py      # ApiResponse[T], ErrorDetail
│   ├── errors.py        # AppError hierarchy + exception handler
│   ├── dependencies.py  # FastAPI Depends: get_current_integration/user
│   ├── middleware.py     # RequestIdMiddleware
│   └── routes/
│       ├── health.py    # GET /health
│       ├── files.py     # POST/GET /v1/files
│       └── jobs.py      # POST/GET /v1/jobs
├── worker/
│   └── main.py          # run_worker() — BRPOP loop, process_job
├── admin/
│   └── app.py           # Starlette admin stub
├── db/
│   ├── models.py        # Pydantic models for all 11 tables
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
│       └── credit_transactions.py # CreditTransactionRepo
├── jobs/
│   ├── fields.py        # InputFile, OutputFile, FileConstraints
│   ├── registry.py      # JobRegistry, @job_handler decorator, discover_handlers
│   ├── context.py       # JobContext[TInput, TOutput]
│   └── handlers/
│       └── remove_bg.py # RemoveBgInput/Output, handle_remove_bg
├── services/
│   ├── auth.py          # generate/verify/hash JWT API keys
│   └── billing.py       # reserve/refund credits, calculate_credit_split
├── providers/
│   ├── base.py          # ProviderAdapter ABC, ProviderResult, ProviderError
│   └── mock.py          # MockProvider (echo or 1x1 PNG)
└── scripts/
    ├── seed.py          # Create test partner+integration+key+provider+job_type
    └── sync_job_types.py # Sync handlers → job_types table
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

## Environment Variables
All prefixed with `AIMG_`. Required (no default): `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `JWT_SECRET`, `ENCRYPTION_KEY`, `ADMIN_SESSION_SECRET`.
See `aimg/common/settings.py` for full list with defaults.
