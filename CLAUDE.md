# AIMG — AI Image Processing B2B2C API

## Overview
B2B2C API for AI image processing. Partners integrate via REST API, submit image processing jobs (background removal, text-to-image, etc.), and receive results. Built with FastAPI + asyncpg + Redis + S3.

## Stack
- **API**: FastAPI, asyncpg (no ORM), redis, aiobotocore (S3)
- **Worker**: asyncio process reading from Redis queue
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
├── __main__.py          # CLI entrypoint: api|worker|admin
├── common/
│   ├── settings.py      # Settings(BaseSettings) — all env vars
│   ├── logging.py       # structlog config, request_id ContextVar
│   ├── connections.py   # create_db_pool, create_redis_client, create_s3_client
│   └── health.py        # check_database, check_redis, check_storage
├── api/
│   ├── app.py           # create_app(settings) factory with lifespan
│   ├── envelope.py      # ApiResponse[T], ErrorDetail
│   ├── dependencies.py  # FastAPI Depends helpers
│   ├── middleware.py     # RequestIdMiddleware
│   └── routes/
│       └── health.py    # GET /health
├── worker/
│   └── main.py          # run_worker() with graceful shutdown
├── admin/
│   └── app.py           # Starlette admin stub
├── db/                  # Future: repositories
├── jobs/                # Future: job handlers
├── services/            # Future: business logic
└── providers/           # Future: AI provider adapters
```

## Commands
```bash
uv sync                              # Install dependencies
uv run pytest tests/unit/            # Unit tests (no infra needed)
uv run pytest tests/functional/      # Functional tests (needs postgres, redis, minio)
uv run pytest tests/e2e/             # E2E tests (needs full docker-compose up)
uv run python -m aimg api            # Start API server
uv run python -m aimg worker         # Start worker
uv run python -m aimg admin          # Start admin panel
docker-compose up -d                 # Start all services
uv run ruff check .                  # Lint
```

## Key Patterns
- **No ORM**: asyncpg with raw SQL, thin repository layer
- **App factory**: `create_app(settings)` — testable with custom settings
- **Lifespan**: connections created at startup, closed at shutdown
- **Request ID**: UUID via middleware → ContextVar → structlog
- **Health endpoint**: plain JSON (not wrapped in envelope), checks all deps
- **Envelope**: `{request_id, success, data, error}` for all v1/ endpoints (not /health)
- **API keys as JWT**: HS256, revocation cache in Redis

## Environment Variables
All prefixed with `AIMG_`. Required (no default): `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `JWT_SECRET`, `ENCRYPTION_KEY`, `ADMIN_SESSION_SECRET`.
See `aimg/common/settings.py` for full list with defaults.
