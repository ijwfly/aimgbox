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

## Testing

Three уровня тестов, от быстрых до полных.

### Unit-тесты (73 теста)

Не требуют инфраструктуры. Используют моки и fakeredis.

```bash
uv sync                       # установить зависимости (один раз)
uv run pytest tests/unit/ -v  # запуск
```

### Functional-тесты

Требуют запущенные postgres, redis, minio (без API/worker/admin).

```bash
docker-compose up -d postgres redis minio  # только инфра
uv run pytest tests/functional/ -v
```

### E2E-тесты (30 тестов)

Полный стек: API + Worker + Admin + все зависимости. Тесты ходят по HTTP в реальные контейнеры.

#### 1. Поднять стек

```bash
docker-compose up -d --build
```

Дождаться готовности (API на `:8010`, Admin на `:8001`).

#### 2. Seed + sync

```bash
docker-compose exec api uv run python -m aimg seed
docker-compose exec api uv run python -m aimg sync-job-types
```

Seed выведет JWT-токен — скопировать его.

#### 3. Запустить тесты

```bash
AIMG_API_KEY=<JWT_TOKEN> uv run pytest tests/e2e/ -v
```

#### Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `AIMG_API_KEY` | — (обязательна) | JWT-токен из `aimg seed` |
| `AIMG_API_URL` | `http://localhost:8010` | URL API-сервера |
| `AIMG_ADMIN_URL` | `http://localhost:8001` | URL админки |
| `AIMG_DB_HOST` | `localhost` | Хост PostgreSQL |
| `AIMG_DB_PORT` | `5433` | Порт PostgreSQL |
| `AIMG_DB_NAME` | `aimg` | Имя БД |
| `AIMG_DB_USER` | `aimg` | Пользователь БД |
| `AIMG_DB_PASSWORD` | `aimg` | Пароль БД |

#### Что покрывают E2E-тесты

**API (test_flow.py):**
- Upload → job → poll → succeeded (AC 1-3)
- GET /v1/jobs/{id}/result → presigned URL (AC 4)
- Credit lifecycle: reserve, unchanged on success, refund on failure (AC 5-7, 9)
- 402 insufficient credits (AC 8)
- Billing topup (AC 10)
- Idempotency: same result, no double-charge (AC 11-12)
- Provider fallback (AC 13), all providers failed → failed (AC 14)
- Webhooks: delivery, payload structure, retry (AC 15-17)
- Rate limit 429 + Retry-After (AC 24)
- i18n: RU/EN error messages (AC 25-26)

**Admin (test_admin.py):**
- Create partner/integration (AC 18)
- Generate/revoke API keys (AC 19)
- View jobs + filters (AC 20)
- Credit adjustment with comment (AC 21)
- CSV export (AC 22)
- Audit log (AC 23)

#### При повторном запуске

Seed идемпотентен — можно запускать повторно. Тесты используют уникальные user ID (uuid4), поэтому не конфликтуют между запусками.

### Lint

```bash
uv run ruff check .
```
