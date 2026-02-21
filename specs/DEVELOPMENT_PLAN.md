# План разработки AIMG

> Связанные документы: [Индекс спецификаций](README.md)

## Контекст

Проект AIMG описан в спецификациях (`specs/`), реализации пока нет. План разработки вертикальными срезами: каждый этап даёт работающие API-эндпоинты, которые можно вызвать и проверить. Это позволяет рано обнаруживать проблемы в дизайне и адаптироваться.

## Решения

- **Пакетный менеджер:** uv (pyproject.toml + uv.lock)
- **Язык кода:** английский (переменные, функции, docstrings). Комментарии и коммиты — можно на русском.
- **CLAUDE.md:** создаётся на этапе 0

## Принципы

- **Вертикальные срезы**: каждый этап — сквозная функциональность от API до БД, с торчащими эндпоинтами
- **Максимальное покрытие тестами**: unit (без зависимостей) + functional (с БД/Redis/S3) + e2e (HTTP к запущенному сервису)
- **Адаптивность**: ранний фидбек от работающих API позволяет корректировать дизайн

---

## Стратегия тестирования

Три уровня тестов, закладываются с этапа 0:

### 1. Unit-тесты (`tests/unit/`)
- **Без внешних зависимостей** — все моки
- Бизнес-логика: биллинг, валидации, JWT, state machine
- `pytest tests/unit/`

### 2. Функциональные тесты (`tests/functional/`)
- **С реальными PostgreSQL, Redis, S3 (MinIO)**
- Repository-слой, транзакции, race conditions
- `pytest tests/functional/`

### 3. E2E тесты (`tests/e2e/`)
- **HTTP-запросы к запущенному сервису** (API + Worker + все зависимости)
- Полные user flows, acceptance criteria
- `pytest tests/e2e/`

### Структура
```
tests/
├── conftest.py
├── unit/
│   └── conftest.py       # моки
├── functional/
│   └── conftest.py       # реальные подключения
└── e2e/
    └── conftest.py       # HTTP-клиент
```

### Правила
- Unit-тесты обязательны для каждого модуля с бизнес-логикой
- Functional-тесты обязательны для каждого repository-класса
- E2E тесты появляются с этапа 1 и расширяются на каждом этапе
- Все зависимости инжектируются (DI) для мокирования
- pytest + pytest-asyncio

---

## Обзор этапов

| Этап | Статус | Работающие API | Можно проверить |
|------|--------|---------------|-----------------|
| 0 | **DONE** | `GET /health` | Сервис жив, подключения работают |
| 1 | **DONE** | + files, jobs, auth | Полный цикл: upload → job → result |
| 2 | TODO | + meta, balance, history | Два реальных job type, fallback, баланс |
| 3 | TODO | + billing, webhooks, i18n | Все /v1/ эндпоинты, все защитные механизмы |
| 4 | TODO | + /admin/ | Полное управление через браузер |
| 5 | TODO | — | Acceptance criteria 100% |

---

## Этап 0: Скелет + инфра + health

**Цель:** Проект запускается, подключается к зависимостям, `GET /health` отвечает.

**Торчащие API:** `GET /health`

- Инициализация Python-проекта (pyproject.toml, uv)
- Структура: `aimg/api/`, `aimg/worker/`, `aimg/admin/`, `aimg/db/`, `aimg/jobs/`, `aimg/common/`, `aimg/services/`, `aimg/providers/`
- Структура тестов: `tests/unit/`, `tests/functional/`, `tests/e2e/`
- Dockerfile (единый образ, три entrypoint), docker-compose.yml
- Конфигурация: Pydantic Settings, все env-переменные из спеки
- Подключения: asyncpg pool, Redis (aioredis/redis-py), S3 (aiobotocore)
- FastAPI app + `GET /health` (проверка PG, Redis, S3)
- Alembic setup
- Структурированные JSON-логи (structlog), `request_id` middleware
- Response envelope: `{request_id, success, data, error}`
- CLAUDE.md
- **Unit:** config parsing/validation
- **Functional:** health endpoint с реальными подключениями
- **E2E:** `GET /health` → 200

**Результат:** `docker-compose up` → `curl /health` → `{"status": "ok"}`

> **Завершён:** commit `bf8b456`. 46 файлов, 2753 строк. Все 5 тестов проходят (3 unit + 1 functional + 1 e2e).
> **Dev-заметка:** порты в docker-compose перемаплены из-за локальных конфликтов: postgres `5433:5432`, api `8010:8000`.

---

## Этап 1: Минимальный сквозной flow (upload → create job → mock result)

**Цель:** Партнёр может загрузить файл, создать джоб, воркер обработает его (mock-провайдером), и партнёр получит результат. Весь путь от HTTP-запроса до результата работает.

**Торчащие API:** `POST /v1/files`, `POST /v1/jobs`, `GET /v1/jobs/{id}`, `GET /v1/files/{file_id}`

Этот этап прокладывает весь путь «вертикально» — от API до воркера. Включает минимально необходимое из каждого слоя:

### БД и миграции
- Alembic миграция: `partners`, `integrations`, `api_keys`, `users`, `files`, `jobs`, `job_types`, `job_type_providers`, `providers`, `job_attempts`, `credit_transactions`
- Pydantic-модели для этих таблиц
- Repository-классы (минимальные): PartnerRepo, IntegrationRepo, ApiKeyRepo, UserRepo, FileRepo, JobRepo, JobTypeRepo, ProviderRepo, CreditTransactionRepo
- Seed-скрипт: тестовый партнёр + интеграция + API-ключ + mock-провайдер + job_type

### Аутентификация
- JWT генерация/верификация (HS256)
- Middleware: `X-API-Key` → integration, `X-External-User-Id` → user (автосоздание)
- Redis: кэш отозванных ключей

### Файлы + S3
- `POST /v1/files` — upload в MinIO, запись в таблицу `files`
- `GET /v1/files/{file_id}` — presigned URL
- S3-клиент: upload, presigned URL генерация

### Job framework (минимальный)
- `@job_handler` декоратор, JobRegistry
- InputFile, OutputFile, FileConstraints, JobContext
- Mock-провайдер (`aimg/providers/mock.py`) — echo: возвращает входной файл как результат
- Один handler: `remove_bg` (с mock-провайдером пока)
- `aimg sync-job-types` CLI

### Биллинг (минимальный)
- reserve_credits при создании джоба (free → paid)
- Начисление free_credits при автосоздании пользователя
- Проверка баланса, HTTP 402 при недостатке

### Создание джоба (API)
- `POST /v1/jobs`: валидация → биллинг → INSERT → LPUSH Redis
- `GET /v1/jobs/{id}`: статус джоба

### Worker (минимальный)
- BRPOP из Redis
- Обработка: status=running → вызов handler → status=succeeded/failed
- Upload результата в S3
- Refund при failure

### Тесты
- **Unit:** JWT, биллинг split (free→paid), FileConstraints, config, envelope, @job_handler регистрация
- **Functional:** repos CRUD, аутентификация (генерация/отзыв ключа), S3 upload/download, create job + credit transaction
- **E2E:** полный flow: auth → upload файла → create job → poll до succeeded → download result. Также: create job без кредитов → 402

**Результат:** `curl POST /v1/files` → `curl POST /v1/jobs` → poll → `succeeded` → download presigned URL

> **Завершён:** commit `e10b07f`. 49 файлов, 3003 строк. 51 тест проходит (26 unit + 22 functional + 3 e2e).
> Alembic миграция (11 таблиц), 10 repository классов (BaseRepo), JWT auth (pyjwt), billing (reserve/refund), mock provider, @job_handler framework, remove_bg handler, POST/GET /v1/files, POST/GET /v1/jobs, worker BRPOP loop, seed + sync-job-types CLI.
> **Dev-заметка:** asyncpg требует регистрации JSON/JSONB кодеков через `set_type_codec` в `_init_connection`. `from __future__ import annotations` ломает `fn.__annotations__` — использовать `typing.get_type_hints(fn)`.

---

## Этап 2: Replicate провайдер + реальные handler'ы + fallback

**Цель:** Джобы выполняются через реальный Replicate API. Fallback между провайдерами работает. Два типа джобов: remove_bg и txt2img.

**Торчащие API:** те же + `GET /v1/meta/job-types`, `GET /v1/users/me/balance`, `GET /v1/users/me/history`

### Replicate адаптер
- `aimg/providers/replicate.py`: ReplicateAdapter
- HTTP-клиент к Replicate API: запуск prediction, polling статуса, получение результата
- Конфигурация через `providers.config` JSONB (модель, версия)
- Шифрование/расшифровка `api_key_encrypted`
- Обработка ошибок Replicate → ProviderError

### Handler: remove_bg (реальный)
- `handle_remove_bg`: вызов Replicate модели (например, `cjwbw/rembg`)
- Fallback через ctx.providers (mock как запасной)

### Handler: txt2img
- `Txt2ImgInput`: prompt, negative_prompt, width, height, output_format
- `handle_txt2img`: вызов Replicate модели (SDXL/Flux)
- Fallback

### Fallback-цепочка
- `job_type_providers` по priority
- При ошибке провайдера → запись в job_attempts → следующий провайдер
- Все исчерпаны → failed + refund

### Дополнительные эндпоинты
- `GET /v1/meta/job-types` — список доступных типов (с input/output schema)
- `GET /v1/users/me/balance` — баланс
- `GET /v1/users/me/history` — история джобов (cursor-based пагинация)

### Тесты
- **Unit:** Replicate adapter request/response парсинг (mock HTTP), fallback logic, cursor encoding, encryption/decryption
- **Functional:** fallback chain с mock-провайдерами (первый fails → второй succeeds), job_attempts записи
- **E2E:** create remove_bg job (mock provider) → succeeded; create txt2img job → succeeded; fallback: первый провайдер fails → второй succeeds; /meta/job-types возвращает оба типа

**Результат:** два работающих типа джобов, fallback, баланс и история через API

---

## Этап 3: Идемпотентность + Rate limiting + Webhooks + Локализация

**Цель:** Все защитные механизмы API работают. Webhooks доставляются. Ошибки локализуются.

**Торчащие API:** + `POST /v1/billing/topup`, `POST /v1/billing/check`, `GET /v1/meta/languages`

### Идемпотентность
- `Idempotency-Key` header → Redis `aimg:idempotency:{integration_id}:{key}`, TTL 24h
- Повтор с тем же ключом → возврат существующего джоба (HTTP 200)

### Rate limiting
- Per-integration (RPM): Redis sliding window, `integrations.rate_limit_rpm`
- Per-user (jobs/hour): Redis sliding window, env `AIMG_USER_RATE_LIMIT_JOBS_PER_HOUR`
- Заголовки: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`
- HTTP 429 при превышении

### Webhooks
- Сервис: формирование payload, HMAC-SHA256 подпись (`X-AIMG-Signature`)
- Доставка: HTTP POST на `integration.webhook_url` при succeeded/failed
- Retry: 3 попытки, backoff (10s, 60s, 300s)
- Таблица `webhook_deliveries`
- Фоновая задача retry в воркере

### Биллинг (расширение)
- `POST /v1/billing/topup` — пополнение (с идемпотентностью через external_transaction_id)
- `POST /v1/billing/check` — проверка хватает ли кредитов
- CLI: `aimg reconcile-balances`

### Локализация
- `locales/en.json`, `locales/ru.json`
- `Accept-Language` / `?lang=` / поле `language` в теле
- `GET /v1/meta/languages`
- Сообщения об ошибках на языке запроса

### Worker (расширение)
- Recovery janitor: зависшие джобы (running > timeout + 60s) → failed + refund
- Orphaned job recovery: pending > 60s → re-enqueue
- Graceful shutdown (SIGTERM)
- Конкурентность: `AIMG_WORKER_CONCURRENCY` (asyncio.Semaphore)

### Тесты
- **Unit:** rate limiter logic, idempotency key, HMAC подпись, webhook payload, backoff расчёт, i18n template rendering, reconciliation алгоритм
- **Functional:** idempotency с реальным Redis, rate limiting, webhook доставка на mock server, recovery janitor, orphaned recovery
- **E2E:** идемпотентность (повтор → 200), rate limit (429 + Retry-After), webhook доставлен при succeeded/failed, topup → баланс увеличен, check → can_afford, ошибки на русском при `Accept-Language: ru`

**Результат:** API полностью функционален для партнёров (все /v1/ эндпоинты работают)

---

## Этап 4: Админ-панель

**Цель:** Полнофункциональная админка. Можно управлять всеми сущностями через браузер.

**Торчащие API:** все `/admin/` эндпоинты

### 4a: Каркас + auth + партнёры/интеграции/ключи
- Starlette app, Jinja2, Pico CSS, htmx
- Миграция: `admin_users`, `audit_log` (если не добавлены ранее)
- Login/logout (bcrypt, session в Redis), роли (super_admin/admin/viewer)
- CRUD партнёров, CRUD интеграций, генерация/отзыв API-ключей
- Audit log для всех мутаций

### 4b: Пользователи + джобы + мониторинг
- Поиск пользователей, просмотр баланса/истории, корректировка кредитов
- Таблица джобов с фильтрами, детали (attempts, файлы)
- Dashboard: активные джобы, джобы/день, расход кредитов, % ошибок
- Экспорт джобов в CSV

### 4c: Типы джобов + провайдеры (super_admin)
- CRUD типов джобов (credit_cost, timeout, status, fallback-цепочка)
- CRUD провайдеров

### htmx-паттерны
- Пагинация без перезагрузки
- Живой поиск (keyup + delay)
- Inline-формы (корректировка кредитов, изменение статуса)
- `hx-confirm` для опасных действий

### Тесты
- **Unit:** bcrypt hashing, session management, role checking, audit log формирование, CSV export
- **Functional:** CRUD через HTTP с реальной БД, audit log записи
- **E2E:** логин → создание партнёра → интеграция → ключ → корректировка кредитов → просмотр джобов → экспорт CSV

**Результат:** админка полностью работает в браузере

---

## Этап 5: Полировка + acceptance criteria

**Цель:** Всё работает вместе. Все 26 acceptance criteria покрыты.

- OpenAPI документация (`/docs`, `/openapi.json`)
- Проверка всех 26 acceptance criteria из секции 24 спеки
- README.md для проекта
- Финальное обновление CLAUDE.md
- **E2E тесты покрывают acceptance criteria:**
  1-4. Основной flow (upload → create → poll → result)
  5-10. Биллинг (резервирование, подтверждение, возврат, 402, баланс ≥ 0, topup)
  11-12. Идемпотентность
  13-14. Fallback провайдеров
  15-17. Webhooks (доставка, подпись, retry)
  18-23. Админка (партнёры, ключи, джобы, кредиты, CSV, аудит)
  24. Rate limiting (429 + Retry-After)
  25-26. Локализация (RU/EN)

**Результат:** `pytest tests/` — все зелёные; 100% acceptance criteria
