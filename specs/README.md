# AIMG — Техническая спецификация

> Версия: 1.0 · Дата: 2026-02-21

**AIMG** — backend-сервис (B2B2C API) для генерации и обработки изображений через AI-провайдеров.

## Стек технологий

Python, FastAPI, PostgreSQL (asyncpg), Redis, S3-compatible storage, htmx (админка)

## Документы

| Файл | Описание | Ключевые сущности |
|---|---|---|
| [01-business-context.md](01-business-context.md) | Бизнес-модель, глоссарий, scope, user stories | Partner, Integration, End User, Job, Credit |
| [02-architecture.md](02-architecture.md) | Компоненты, ADR, провайдеры, типы джобов | FastAPI, Worker, Redis Queue, ProviderAdapter, JobType |
| [03-job-handlers.md](03-job-handlers.md) | Реализация джобов: декоратор, модели, примеры | @job_handler, InputFile, OutputFile, JobContext |
| [04-database-schema.md](04-database-schema.md) | Все таблицы БД, файловое хранилище S3 | partners, integrations, users, jobs, credit_transactions |
| [05-api.md](05-api.md) | Принципы API, эндпоинты, ошибки, webhooks | REST endpoints, error codes, webhook payload |
| [06-business-logic.md](06-business-logic.md) | State machine, биллинг, rate limiting, idempotency | Job states, credit flow, двухфазное резервирование |
| [07-admin-and-operations.md](07-admin-and-operations.md) | Админка, NFR, деплой, i18n, критерии приёмки | htmx, Docker, env variables, acceptance criteria |

## Порядок чтения

1. **01-business-context** — понять что делает сервис и зачем
2. **02-architecture** — как устроена система, ключевые решения
3. **04-database-schema** — модель данных
4. **03-job-handlers** — как реализуются задания
5. **05-api** — API-контракт для партнёров
6. **06-business-logic** — state machine, биллинг, защита от ошибок
7. **07-admin-and-operations** — админка, деплой, приёмка
