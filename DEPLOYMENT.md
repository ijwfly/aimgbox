# AIMG — Server Setup Guide

## Prerequisites

- Python 3.12+ with [uv](https://docs.astral.sh/uv/)
- PostgreSQL 16+
- Redis 7+
- S3-compatible storage (AWS S3 or MinIO)
- [Replicate](https://replicate.com) account with API token

## 1. Environment Variables

Create `.env` (or set in your environment / systemd / docker):

```bash
# Database
AIMG_DATABASE_URL=postgresql://aimg:STRONG_PASSWORD@db-host:5432/aimg

# Redis
AIMG_REDIS_URL=redis://redis-host:6379/0

# S3
AIMG_S3_ENDPOINT=https://s3.amazonaws.com   # or MinIO URL
AIMG_S3_ACCESS_KEY=your-s3-access-key
AIMG_S3_SECRET_KEY=your-s3-secret-key
AIMG_S3_BUCKET=aimg

# Auth — generate strong random values
AIMG_JWT_SECRET=$(openssl rand -base64 32)
AIMG_ENCRYPTION_KEY=$(openssl rand -base64 32)
AIMG_ADMIN_SESSION_SECRET=$(openssl rand -base64 32)

# Replicate (needed for migration 004)
REPLICATE_API_TOKEN=r8_your_token_here

# Optional
AIMG_LOG_LEVEL=INFO
AIMG_WORKER_CONCURRENCY=5
```

## 2. Install Dependencies

```bash
uv sync --no-dev    # production deps only
```

## 3. Create Database

```bash
createdb aimg
# or via psql:
psql -c "CREATE DATABASE aimg"
```

## 4. Run Migrations

This creates all tables AND seeds providers + job types:

```bash
uv run alembic upgrade head
```

Migration 004 automatically:
- Creates `replicate`, `mock`, `failing_mock` providers
- Creates `remove_bg`, `txt2img`, `img2img`, `test_allfail` job types
- Links Replicate provider to all job types with correct model configs
- Encrypts the Replicate API token using `AIMG_ENCRYPTION_KEY`

> If you forgot `REPLICATE_API_TOKEN` during migration, update manually:
> ```bash
> uv run python -c "
> from aimg.common.encryption import encrypt_value
> import os
> print(encrypt_value(os.environ['REPLICATE_API_TOKEN'], os.environ['AIMG_ENCRYPTION_KEY']))
> "
> # Then in psql:
> UPDATE providers SET api_key_encrypted='<output>' WHERE slug='replicate';
> ```

## 5. Create Admin User

```bash
uv run python -m aimg create-admin \
    --username admin \
    --password YOUR_STRONG_PASSWORD \
    --role super_admin
```

## 6. Create Partner + Integration + API Key

Use the admin panel or seed script:

```bash
uv run python -m aimg seed
```

This creates a test partner, integration (10 free credits), and prints the JWT API key.

For production, create partners/integrations via the admin panel at `http://host:8001/admin/`.

## 7. Start Services

Three processes need to run:

```bash
# API server (default port 8000)
uv run python -m aimg api

# Background worker (processes jobs via Replicate)
uv run python -m aimg worker

# Admin panel (default port 8001)
uv run python -m aimg admin
```

With systemd, create a unit file for each. Example for API:

```ini
[Unit]
Description=AIMG API
After=postgresql.service redis.service

[Service]
Type=simple
User=aimg
WorkingDirectory=/opt/aimg
EnvironmentFile=/opt/aimg/.env
ExecStart=/opt/aimg/.venv/bin/python -m aimg api
Restart=always

[Install]
WantedBy=multi-user.target
```

## 8. Verify

```bash
# Health check
curl http://localhost:8000/health

# Should return:
# {"status":"ok","version":"1.0.0","dependencies":{"database":"ok","redis":"ok","storage":"ok"}}
```

## Quick Reference

| Service | Default Port | Command |
|---------|-------------|---------|
| API     | 8000        | `python -m aimg api` |
| Worker  | —           | `python -m aimg worker` |
| Admin   | 8001        | `python -m aimg admin` |

| Job Type | Model | Endpoint |
|----------|-------|----------|
| `remove_bg` | `851-labs/background-remover` | version-based, sync mode |
| `txt2img` | `stability-ai/sdxl` | version-based |
| `img2img` | `prunaai/p-image-edit` | model-based |
