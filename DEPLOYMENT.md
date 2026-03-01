# AIMG — Deployment Guide

## Quick Start (docker-compose)

### 1. Configure `.env`

```bash
cp .env .env  # уже есть шаблон, заполни значения
```

Обязательные переменные:

```bash
AIMG_DATABASE_URL=postgresql://aimg:aimg@postgres:5432/aimg
AIMG_REDIS_URL=redis://redis:6379/0
AIMG_S3_ENDPOINT=http://minio:9000
AIMG_S3_ACCESS_KEY=minioadmin
AIMG_S3_SECRET_KEY=minioadmin
AIMG_S3_BUCKET=aimg
AIMG_JWT_SECRET=<сгенерируй: openssl rand -base64 32>
AIMG_ENCRYPTION_KEY=<сгенерируй: openssl rand -base64 32>
AIMG_ADMIN_SESSION_SECRET=<сгенерируй: openssl rand -base64 32>
REPLICATE_API_TOKEN=r8_your_token_here
```

> `REPLICATE_API_TOKEN` нужен при первом запуске — миграция 004 шифрует его и сохраняет в БД. После этого переменная больше не нужна.

### 2. Запуск

```bash
docker-compose up -d --build
```

Это автоматически:
1. Поднимет postgres, redis, minio
2. Запустит `migrate` — создаст таблицы, провайдеров, job types
3. После миграции запустит `api`, `worker`, `admin`

### 3. Создание админа

```bash
docker-compose run --rm api create-admin \
    --username admin \
    --password STRONG_PASSWORD \
    --role super_admin
```

### 4. Создание партнёра + API ключа

```bash
docker-compose run --rm api seed
```

Выведет JWT токен для API. Для прода — создавай партнёров через админку.

### 5. Проверка

```bash
# Health check
curl http://localhost:8010/health

# Job types
curl http://localhost:8010/v1/meta/job-types \
  -H "X-API-Key: <JWT>"
```

## Сервисы

| Сервис   | Порт  | Описание |
|----------|-------|----------|
| api      | 8010  | REST API |
| worker   | —     | Обработка jobs через Replicate |
| admin    | 8001  | Админ-панель |
| postgres | 5433  | БД (хост-порт) |
| redis    | 6379  | Очередь + кэш |
| minio    | 9000/9001 | S3 хранилище / консоль |

## Job Types

| Slug | Модель | Описание |
|------|--------|----------|
| `remove_bg` | `851-labs/background-remover` | Удаление фона (sync mode, ~3s) |
| `txt2img` | `stability-ai/sdxl` | Генерация из текста (~12s) |
| `img2img` | `prunaai/p-image-edit` | Редактирование по промпту (~6s) |

## Обновление

```bash
git pull
docker-compose up -d --build
```

Миграции запускаются автоматически при каждом старте (сервис `migrate`). Alembic идемпотентен — повторный запуск ничего не сломает.

## Обновление Replicate токена

Если нужно сменить токен без пересоздания БД:

```bash
docker-compose run --rm api python -c "
from aimg.common.encryption import encrypt_value
import os
print(encrypt_value(
    os.environ['REPLICATE_API_TOKEN'],
    os.environ['AIMG_ENCRYPTION_KEY'],
))
"
```

Затем в psql:
```sql
UPDATE providers SET api_key_encrypted='<output>' WHERE slug='replicate';
```

## Логи

```bash
docker-compose logs -f worker    # логи воркера
docker-compose logs -f api       # логи API
docker-compose logs -f migrate   # результат миграции
```
