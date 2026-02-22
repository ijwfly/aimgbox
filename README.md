# AIMG

B2B2C API for AI image processing. Partners integrate via REST API, submit image processing jobs (background removal, text-to-image, etc.), and get results via polling or webhooks.

Built with FastAPI + asyncpg + Redis + S3. Admin panel on Starlette + Jinja2 + htmx.

For detailed architecture and specs see [specs/](specs/).

## Quick Start

### 1. Start infrastructure

```bash
docker-compose up -d
```

This starts: postgres (`:5433`), redis (`:6379`), minio (`:9000`), api (`:8010`), worker, admin (`:8001`).

### 2. Run migrations

```bash
AIMG_DATABASE_URL="postgresql://aimg:aimg@localhost:5433/aimg" uv run alembic upgrade head
```

### 3. Seed data

The fastest path — seed creates everything at once:

```bash
docker-compose exec api uv run python -m aimg seed
```

Creates: partner, integration, API key (JWT), providers (mock + replicate), job types (remove_bg + txt2img), admin user `admin`/`admin`. **Prints the JWT token** — save it.

Or create just the admin user manually:

```bash
uv run python -m aimg create-admin --username admin --password admin --role super_admin \
  --database-url "postgresql://aimg:aimg@localhost:5433/aimg"
```

### 4. Configure via admin panel

Open http://localhost:8001/admin/login — `admin` / `admin`

If you ran seed — everything is already set up, skip to step 5. From scratch:

1. **Partners** — New — enter a name
2. **Integrations** — New — select partner, give it a name
3. On the integration page — **Generate API Key** — copy the JWT (shown only once!)
4. **Providers** — New — slug `mock`, adapter class `mock`, any api key
5. **Job Types** — run sync to register handlers:
   ```bash
   docker-compose exec api uv run python -m aimg sync-job-types
   ```
   Then in admin open each job type and add the provider.

### 5. Submit a job

```bash
# txt2img — no file upload needed
curl -X POST http://localhost:8010/v1/jobs \
  -H "X-API-Key: <JWT_TOKEN>" \
  -H "X-External-User-Id: user-1" \
  -H "Content-Type: application/json" \
  -d '{"job_type": "txt2img", "input": {"prompt": "a cat in space"}}'
```

Or `remove_bg` (upload a file first):

```bash
# Upload image
curl -X POST http://localhost:8010/v1/files \
  -H "X-API-Key: <JWT_TOKEN>" \
  -H "X-External-User-Id: user-1" \
  -F "file=@photo.png"
# returns file_id

# Create job
curl -X POST http://localhost:8010/v1/jobs \
  -H "X-API-Key: <JWT_TOKEN>" \
  -H "X-External-User-Id: user-1" \
  -H "Content-Type: application/json" \
  -d '{"job_type": "remove_bg", "input": {"image": "<FILE_ID>"}}'
```

### 6. Check status

```bash
curl http://localhost:8010/v1/jobs/<JOB_ID> \
  -H "X-API-Key: <JWT_TOKEN>" \
  -H "X-External-User-Id: user-1"
```

The worker picks up the job automatically. Mock provider returns results immediately.

## Services

| Service | Port | Description |
|---------|------|-------------|
| API | 8010 | REST API for partners |
| Admin | 8001 | Admin panel (Starlette + htmx) |
| Worker | — | Background job processor |
| PostgreSQL | 5433 | Database |
| Redis | 6379 | Queue, cache, sessions |
| MinIO | 9000 | S3-compatible storage |

## Development

```bash
uv sync                              # Install dependencies
uv run pytest tests/unit/            # Unit tests (no infra needed)
uv run pytest tests/functional/      # Functional tests (needs postgres, redis, minio)
uv run ruff check .                  # Lint
```
