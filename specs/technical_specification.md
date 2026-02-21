# AIMG — Техническая спецификация

> Версия: 1.0
> Дата: 2026-02-21
> Стек: Python, FastAPI, PostgreSQL (asyncpg), Redis, S3-compatible storage, htmx (админка)

---

# Часть I. Бизнес-контекст

## 1. Введение и бизнес-модель

AIMG — backend-сервис (B2B2C API), который предоставляет партнёрам единый интерфейс для генерации и обработки изображений (и в перспективе видео) с помощью AI-провайдеров.

**Схема работы:**

```
Конечный пользователь → Фронт партнёра (бот, сайт) → AIMG API → AI-провайдер (Replicate, Stability AI, …)
```

**Что делает AIMG:**
- Принимает запросы от партнёров через REST API
- Управляет очередью задач и выполняет их через AI-провайдеров
- Ведёт биллинг (бесплатные + платные кредиты)
- Хранит входные и выходные файлы в S3
- Обеспечивает fallback между провайдерами при ошибках
- Предоставляет админ-панель для управления

**Что НЕ делает AIMG:**
- Не предоставляет UI для конечных пользователей (это ответственность партнёра)
- Не принимает платежи напрямую (оплата на стороне партнёра или внешнего шлюза)

---

## 2. Глоссарий

| Термин | Описание |
|---|---|
| **Partner** | Организация, получающая доступ к API. Может иметь несколько интеграций. |
| **Integration** | Конкретная точка подключения партнёра (Telegram-бот, сайт, мобильное приложение). У каждой интеграции свои API-ключи и пространство пользователей. |
| **End User** | Конечный пользователь, инициирующий обработку через фронт партнёра. Идентифицируется по `external_user_id` в рамках интеграции. |
| **external_user_id** | Строковый идентификатор пользователя, задаваемый партнёром. Может быть Telegram user ID, UUID, email — партнёр решает сам. |
| **Job** | Задание на обработку. Имеет тип, входные данные, статус и результат. |
| **JobType** | Тип задания (например, `remove_bg`, `txt2img`, `upscale_2x`). Определяет входные параметры, стоимость, допустимые форматы и цепочку провайдеров. |
| **Provider** | Внешний AI-сервис (Replicate, Stability AI, OpenAI DALL-E и т.д.), выполняющий фактическую обработку. |
| **ProviderAdapter** | Программный адаптер, реализующий интерфейс взаимодействия с конкретным провайдером. |
| **Credit** | Единица списания. Стоимость в кредитах определяется типом джоба. |
| **Free credits** | Начальные бесплатные кредиты, выдаваемые пользователю при первом обращении. Количество настраивается per integration. |
| **Paid credits** | Кредиты, пополненные через партнёра или администратора. |
| **Idempotency-Key** | Ключ идемпотентности, предотвращающий повторное создание джоба и двойное списание при retry. |
| **Webhook** | HTTP callback, отправляемый AIMG на URL партнёра при завершении джоба. |

---

## 3. Область работ

### 3.1 Входит в v1

- REST API (`/v1/`) для создания заданий, получения результатов, управления балансом
- Загрузка файлов через отдельный endpoint
- Авторизация партнёров через JWT-based API-ключи
- Полная модель данных: партнёры, интеграции, пользователи, джобы, биллинг, аудит
- Система типов джобов с конфигурируемыми параметрами и стоимостью
- Двухфазный биллинг (резервирование → подтверждение/возврат)
- Fallback между провайдерами при ошибках
- Webhook-нотификации при завершении джобов
- Админ-панель: управление партнёрами, интеграциями, ключами, пользователями, кредитами, джобами
- Rate limiting (per-integration, per-user)
- Локализация системных сообщений (RU/EN)
- Docker-деплой, OpenAPI документация

### 3.2 Не входит в v1

- Приём платежей (оплата на стороне партнёра/внешнего шлюза)
- Фронтенды партнёров (боты, сайты)
- Контент-фильтры / NSFW-модерация
- Пакетная обработка (несколько файлов одним запросом)
- Политики удаления данных (хранение бессрочно)

### 3.3 Кандидаты на v2

- Batch-обработка (массовая загрузка)
- SSE/WebSocket для real-time обновлений статуса
- Shared-баланс между интеграциями одного партнёра
- Data retention policies с автоматической очисткой S3
- Расширенная аналитика в админке
- SDK для партнёров (Python, JS)

---

## 4. Пользовательские сценарии

### 4.1 Создание задания (image-to-image)

1. Партнёр загружает файл через `POST /v1/files` и получает `file_id`
2. Партнёр вызывает `POST /v1/jobs` с указанием `job_type` и объектом `input` (содержит `file_id` и параметры)
3. Сервис валидирует формат/размер файла, проверяет доступ интеграции к данному типу джоба
4. Сервис проверяет баланс пользователя. Если кредитов недостаточно — HTTP 402, джоб не создаётся
5. Сервис резервирует кредиты, создаёт джоб со статусом `pending`, помещает задачу в Redis-очередь
6. Возвращает `201 Created` с данными джоба

### 4.2 Создание задания (text-to-image)

1. Партнёр вызывает `POST /v1/jobs` с `job_type` и текстовым `prompt` в параметрах (без файла)
2. Далее аналогично п. 4.1, шаги 3–6

### 4.3 Получение результата (polling)

1. Партнёр опрашивает `GET /v1/jobs/{job_id}` до получения терминального статуса (`succeeded` / `failed`)
2. При `succeeded` — вызывает `GET /v1/jobs/{job_id}/result` для получения presigned URL
3. При `failed` — показывает пользователю локализованное сообщение об ошибке

### 4.4 Получение результата (webhook)

1. У интеграции настроен `webhook_url`
2. При переходе джоба в `succeeded` или `failed` AIMG отправляет POST на `webhook_url`
3. Партнёр верифицирует подпись и обрабатывает результат
4. Polling остаётся доступен как fallback

### 4.5 Недостаток кредитов

1. Партнёр вызывает `POST /v1/jobs`
2. Баланс пользователя меньше стоимости джоба
3. Сервис возвращает HTTP 402 с кодом `INSUFFICIENT_CREDITS`, указывая необходимое и доступное количество
4. Джоб не создаётся, кредиты не списываются

### 4.6 Предварительная проверка баланса

1. Партнёр вызывает `POST /v1/billing/check` с типом джоба
2. Сервис возвращает `can_afford: true/false` и текущий баланс
3. Партнёр показывает пользователю UI в зависимости от результата

### 4.7 Пополнение кредитов

1. Партнёр принимает оплату на своей стороне
2. Вызывает `POST /v1/billing/topup` с суммой и `external_transaction_id`
3. Кредиты зачисляются, баланс обновляется

### 4.8 Fallback при ошибке провайдера

1. Воркер отправляет задание первому провайдеру из цепочки
2. Провайдер возвращает ошибку
3. Воркер записывает попытку в `job_attempts`, переходит к следующему провайдеру
4. Если все провайдеры исчерпаны — джоб переходит в `failed`, кредиты возвращаются

### 4.9 Идемпотентность

1. Партнёр отправляет `POST /v1/jobs` с `Idempotency-Key: abc123`
2. Из-за сетевой ошибки партнёр не получает ответ и повторяет запрос с тем же ключом
3. Сервис обнаруживает существующий ключ, возвращает ранее созданный джоб (HTTP 200)
4. Повторное списание не происходит

### 4.10 Администратор создаёт партнёра и выдаёт ключи

1. Админ создаёт партнёра через админку
2. Создаёт интеграцию для партнёра
3. Генерирует API-ключ для интеграции
4. Передаёт ключ партнёру через безопасный канал

### 4.11 Администратор корректирует кредиты

1. Админ находит пользователя по `external_user_id`
2. Начисляет или списывает кредиты с обязательным комментарием причины
3. Действие записывается в audit log

### 4.12 Администратор отзывает API-ключ

1. Админ выбирает ключ интеграции и нажимает "Отозвать"
2. Ключ помечается как отозванный, запросы с ним перестают приниматься
3. Партнёр получает HTTP 401 при попытке использовать старый ключ

---

# Часть II. Архитектура

## 5. Архитектура системы

### 5.1 Компоненты

```
┌──────────────────────────────────────────────────────────────┐
│                        Docker Compose                         │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │  FastAPI App  │  │  Worker      │  │  Admin Panel │       │
│  │  (REST API)   │  │  (asyncio)   │  │  (htmx)      │       │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘       │
│         │                  │                  │               │
│         ▼                  ▼                  ▼               │
│  ┌──────────────┐   ┌──────────────┐                         │
│  │  PostgreSQL   │   │    Redis     │                         │
│  │              │   │  (очередь)   │                         │
│  └──────────────┘   └──────────────┘                         │
│         │                                                     │
│         ▼                                                     │
│  ┌──────────────┐                                             │
│  │  MinIO / S3   │                                            │
│  └──────────────┘                                             │
└──────────────────────────────────────────────────────────────┘
```

- **FastAPI App** — REST API (v1), OpenAPI-документация. Точка входа для партнёрских HTTP-запросов.
- **Worker** — asyncio-процесс, читает задачи из Redis-очереди, выполняет через провайдеров, записывает результат в S3 и обновляет статус в PostgreSQL.
- **Admin Panel** — отдельный Python-сервер на Starlette + Jinja2 + htmx. Не встроен в FastAPI. Подключается к тем же PostgreSQL и Redis. Отдельная точка входа в Docker-образе.
- **PostgreSQL** — основное хранилище: партнёры, интеграции, пользователи, джобы, биллинг, аудит. Доступ через asyncpg (без ORM, с тонким repository-слоем).
- **Redis** — очередь задач для воркеров, кэш отозванных API-ключей, счётчики rate limiting, хранение идемпотентных ключей.
- **S3 (MinIO)** — хранение входных и выходных файлов.

### 5.2 Flow обработки запроса

```
Partner → POST /v1/jobs
  │
  ├─ 1. Auth: проверка JWT (подпись + кэш отзыва в Redis)
  ├─ 2. Resolve user: поиск/автосоздание по (integration_id, external_user_id)
  ├─ 3. Validate: тип джоба, параметры, формат файла
  ├─ 4. Billing: проверка баланса, резервирование кредитов (PostgreSQL-транзакция)
  ├─ 5. Create job: INSERT в jobs (status=pending)
  ├─ 6. Enqueue: LPUSH задачи в Redis-очередь
  └─ 7. Response: 201 Created

Worker (asyncio loop):
  │
  ├─ 1. BRPOP из Redis-очереди
  ├─ 2. UPDATE jobs SET status=running
  ├─ 3. Вызов провайдера (1-й в цепочке fallback)
  │     ├─ Успех → сохранение результата в S3, status=succeeded, коммит кредитов
  │     └─ Ошибка → запись в job_attempts, попытка следующего провайдера
  │           └─ Все провайдеры исчерпаны → status=failed, возврат кредитов
  ├─ 4. Fire webhook (если настроен)
  └─ 5. Возврат к шагу 1
```

---

## 6. Архитектурные решения (ADR)

### ADR-1: Единый `external_user_id`

**Решение:** Партнёры идентифицируют пользователей единым строковым полем `external_user_id`. Telegram user ID, email, UUID — не имеет значения. AIMG не интерпретирует значение этого поля.

**Обоснование:** Наличие отдельного `telegram_user_id` создаёт путаницу и привилегирует один тип интеграции. Унификация упрощает API и модель данных.

### ADR-2: Пользователь привязан к интеграции

**Решение:** Пользователь идентифицируется парой `(integration_id, external_user_id)`. У каждой интеграции — своё пространство пользователей и балансов.

**Обоснование:** Партнёр может иметь несколько интеграций с разными схемами идентификации. Привязка к интеграции исключает коллизии ID.

**Следствие:** Один физический человек, использующий две интеграции одного партнёра — это два разных пользователя в AIMG. Shared-баланс — кандидат на v2.

### ADR-3: Redis-очередь задач

**Решение:** Очередь задач реализуется через Redis (BRPOP/LPUSH или Redis Streams). Воркер — отдельный asyncio-процесс, читающий задачи из очереди.

**Обоснование:** Redis обеспечивает надёжную и быструю доставку сообщений. В отличие от PG-based queue (`SELECT FOR UPDATE SKIP LOCKED`), Redis не нагружает основную БД и даёт предсказуемую латентность. В отличие от Celery — минимальная сложность, полный контроль над логикой retry и fallback.

**Детали реализации:**
- Очередь: Redis List с ключом `aimg:jobs:queue`
- Формат сообщения: JSON `{"job_id": "uuid", "job_type": "slug", "attempt": 1}`
- Processing list: `aimg:jobs:processing` (через `BRPOPLPUSH` для at-least-once delivery)
- При успешной обработке — удаление из processing list
- При crash воркера — recovery: периодическая проверка processing list на зависшие задачи (по timestamp)

### ADR-4: Отдельный endpoint загрузки файлов

**Решение:** Файлы загружаются через `POST /v1/files`, который возвращает `file_id`. Создание джоба (`POST /v1/jobs`) принимает `file_id` в полях объекта `input`.

**Обоснование:** Разделение (a) упрощает endpoint создания джоба (чистый JSON, не multipart), (b) позволяет переиспользовать загруженные файлы, (c) даёт возможность вынести upload на отдельный сервер в будущем.

### ADR-5: Стоимость per JobType

**Решение:** Каждый `JobType` определяет `credit_cost` (целое число). Разные типы джобов стоят по-разному.

**Обоснование:** Плоская стоимость (1 джоб = 1 кредит) не отражает реальность — генерация видео дороже удаления фона. Per-JobType pricing — простой и достаточный механизм для v1.

### ADR-6: Webhooks + Polling

**Решение:** Поддерживаются оба механизма. Партнёр может настроить `webhook_url` для интеграции. При завершении джоба AIMG отправляет POST. Polling через `GET /v1/jobs/{id}` доступен всегда.

**Обоснование:** Polling прост, но неэффективен. Webhooks эффективны, но требуют endpoint на стороне партнёра. Поддержка обоих даёт партнёрам гибкость.

### ADR-7: API-ключи как JWT

**Решение:** API-ключи — JWT-токены, содержащие `integration_id`, `partner_id`, `key_id` и `issued_at`. Верификация по подписи (без обращения к БД на каждый запрос). Отзыв — через кэш отозванных ключей в Redis.

**Детали:**
- Алгоритм подписи: HS256
- Secret: конфигурируется через env-переменную `AIMG_JWT_SECRET`
- TTL ключа: не ограничен (ротация через отзыв и перевыпуск)
- Кэш отзыва: Redis set `aimg:revoked_keys`, проверяется при каждом запросе

### ADR-8: Автосоздание пользователей

**Решение:** Пользователи создаются автоматически при первом запросе. Когда приходит `external_user_id`, не существующий для данной интеграции, AIMG создаёт запись и начисляет `integration.default_free_credits`.

**Обоснование:** Партнёрам не нужно управлять жизненным циклом пользователей на нашей стороне. API проще, интеграция быстрее.

### ADR-9: asyncpg без ORM

**Решение:** Взаимодействие с PostgreSQL — через asyncpg напрямую. Без SQLAlchemy, без ORM. Тонкий repository-слой оборачивает сырые запросы.

**Обоснование:** asyncpg — самый быстрый асинхронный драйвер для PostgreSQL в Python. ORM избыточен для проекта с чётко определённой схемой и ограниченным набором запросов. Repository-слой обеспечивает переиспользование и тестируемость без магии ORM.

**Структура:**
```python
# repos/users.py
class UserRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_or_create(self, integration_id: UUID, external_user_id: str, default_free_credits: int) -> User:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO users (integration_id, external_user_id, free_credits) "
                "VALUES ($1, $2, $3) "
                "ON CONFLICT (integration_id, external_user_id) DO NOTHING "
                "RETURNING *",
                integration_id, external_user_id, default_free_credits
            )
            if row is None:
                row = await conn.fetchrow(
                    "SELECT * FROM users WHERE integration_id = $1 AND external_user_id = $2",
                    integration_id, external_user_id
                )
            return User(**row)
```

Модели данных (для сериализации, не ORM-модели) определяются через Pydantic.

### ADR-10: Админка как отдельный сервис на htmx

**Решение:** Админ-панель — отдельный Python-сервер (Starlette + Jinja2 + htmx), не встроенный в FastAPI. Отдельная точка входа в Docker-образе (`admin`).

**Обоснование:**
- Разделение ответственности: API-сервер обслуживает партнёров, админка — внутреннюю команду
- htmx обеспечивает интерактивность без тяжёлого JS-фреймворка (React/Vue не нужны для внутренней админки)
- Starlette — легковесный ASGI-фреймворк, достаточный для серверного рендеринга
- Общий доступ к PostgreSQL и Redis через те же репозитории и модели
- Независимый деплой и масштабирование при необходимости

**Стек админки:**
- Starlette (HTTP-фреймворк)
- Jinja2 (шаблоны)
- htmx (динамическая интерактивность: фильтры, поиск, пагинация, формы без перезагрузки)
- Простой CSS (Pico CSS или аналог — минимальный classless-фреймворк)

### ADR-11: Биллинг — транзакционный журнал как source of truth

**Решение:** Таблица `credit_transactions` является единственным источником истины о балансах. Поля `users.free_credits` и `users.paid_credits` — денормализованный кэш, который можно пересчитать из транзакций в любой момент. Все операции с кредитами (списание, возврат, пополнение, корректировка) выполняются в одной PostgreSQL-транзакции: запись в `credit_transactions` + обновление кэша в `users`.

**Обоснование:** При падении воркера после списания кредитов, но до завершения джоба, наличие полного журнала транзакций позволяет восстановить корректный баланс. Денормализация на `users` — для скорости чтения, но она всегда верифицируема.

**Механизмы защиты:**
1. **Атомарность:** Списание + запись транзакции + создание/обновление джоба — в одной PG-транзакции. Либо всё происходит, либо ничего.
2. **Recovery janitor:** Периодический процесс находит джобы в `running` дольше `timeout_seconds + grace_period`, помечает их как `failed` и возвращает кредиты.
3. **Reconciliation:** CLI-команда `aimg reconcile-balances` пересчитывает `users.free_credits` и `users.paid_credits` из суммы `credit_transactions`. Запускается при подозрении на расхождение или по расписанию.
4. **Orphaned jobs:** При старте воркера — проверка джобов в `pending`, которые есть в БД, но отсутствуют в Redis-очереди (lost enqueue). Повторная постановка в очередь.

---

## 7. Абстракция провайдеров

### 7.1 Интерфейс адаптера

```python
class ProviderAdapter(ABC):
    """Базовый интерфейс для всех провайдеров AI-обработки."""

    @abstractmethod
    async def execute(self, job: Job, params: dict) -> ProviderResult:
        """Выполнить задание. Возвращает результат или выбрасывает ProviderError."""
        ...

    @abstractmethod
    async def validate_params(self, job_type: JobType, params: dict) -> bool:
        """Проверить допустимость параметров для данного провайдера."""
        ...
```

```python
@dataclass
class ProviderResult:
    output_data: bytes          # содержимое результата
    content_type: str           # MIME-тип (image/png, video/mp4, ...)
    provider_job_id: str | None # ID задания на стороне провайдера
    metadata: dict              # дополнительные данные от провайдера
```

### 7.2 Регистрация провайдеров

Провайдеры хранятся в таблице `providers` со ссылкой на Python-класс адаптера (`adapter_class`). При старте приложения адаптеры загружаются динамически.

### 7.3 Fallback-цепочка

Для каждого `JobType` в таблице `job_type_providers` задаётся упорядоченный список провайдеров. При ошибке воркер переходит к следующему. Каждая попытка записывается в `job_attempts`.

---

## 8. Система типов джобов

`JobType` существует на двух уровнях:

**В коде** (через `@job_handler`):
- `slug` — уникальный идентификатор
- `name`, `description` — метаданные для API и админки
- `input_model` — Pydantic-модель входных данных (включая файлы, тексты, параметры)
- `output_model` — Pydantic-модель выходных данных
- `handler` — async-функция, реализующая логику

**В БД** (через таблицу `job_types`, настраивается в админке):
- `credit_cost` — стоимость в кредитах
- `timeout_seconds` — таймаут выполнения
- `status` — `active` / `disabled`
- `input_schema` / `output_schema` — JSON Schema, сгенерированная из Pydantic-моделей (для документации и API)

**Принцип разделения:** Код определяет *что* делает джоб и *какие данные* он принимает/возвращает. БД определяет *сколько стоит*, *как долго ждать* и *через каких провайдеров* выполнять. Это позволяет менять цены и настройки без передеплоя.

Доступ интеграций к типам джобов контролируется через `integration_job_types`. Если для интеграции нет записей — доступны все активные типы.

---

## 9. Реализация джобов (Job Handlers)

Джобы реализуются как Python-функции, помеченные декоратором `@job_handler`. Входные и выходные данные описываются Pydantic-моделями целиком — включая файлы, тексты и любые параметры. Это обеспечивает полную типизацию, автоматическую валидацию и генерацию JSON Schema для API-документации.

### 9.1 Типы полей для ввода/вывода

Фреймворк предоставляет специальные аннотированные типы для работы с файлами:

```python
from aimg.jobs.fields import InputFile, OutputFile, FileConstraints
from typing import Annotated

# InputFile — ссылка на загруженный файл. В API передаётся как file_id (UUID).
# Фреймворк автоматически загружает содержимое из S3 перед вызовом handler'а.
# FileConstraints задаёт ограничения — валидируются при создании джоба.

ImageInput = Annotated[InputFile, FileConstraints(max_size_mb=20, formats=["png", "jpg", "webp"])]
VideoInput = Annotated[InputFile, FileConstraints(max_size_mb=500, formats=["mp4", "mov", "webm"])]

# OutputFile — результат обработки.
# Handler возвращает OutputFile с данными, фреймворк загружает их в S3.
```

```python
@dataclass
class InputFile:
    """Резолвленный входной файл. Handler получает уже загруженные данные."""
    file_id: UUID
    data: bytes
    content_type: str
    original_filename: str | None
    size_bytes: int

@dataclass
class OutputFile:
    """Результат обработки для загрузки в S3."""
    data: bytes
    content_type: str
    filename: str | None = None  # если не задан — генерируется автоматически
```

### 9.2 Пример: image-to-image (remove_bg)

```python
from pydantic import BaseModel, Field
from aimg.jobs.registry import job_handler
from aimg.jobs.fields import InputFile, OutputFile, FileConstraints
from aimg.jobs.context import JobContext

class RemoveBgInput(BaseModel):
    """Входные данные для удаления фона."""
    image: Annotated[InputFile, FileConstraints(max_size_mb=20, formats=["png", "jpg", "webp"])]
    output_format: Literal["png", "webp"] = "png"

class RemoveBgOutput(BaseModel):
    """Результат удаления фона."""
    image: OutputFile

@job_handler(
    slug="remove_bg",
    name="Remove Background",
    description="Removes background from an image using AI",
)
async def handle_remove_bg(ctx: JobContext[RemoveBgInput, RemoveBgOutput]) -> RemoveBgOutput:
    for provider in ctx.providers:
        try:
            result = await provider.execute(
                input_data=ctx.input.image.data,
                params={"output_format": ctx.input.output_format},
            )
            return RemoveBgOutput(
                image=OutputFile(
                    data=result.output_data,
                    content_type=f"image/{ctx.input.output_format}",
                )
            )
        except ProviderError as e:
            ctx.record_attempt(provider=provider, error=e)
            continue

    raise AllProvidersFailed()
```

### 9.3 Пример: text-to-image (txt2img)

```python
class Txt2ImgInput(BaseModel):
    """Входные данные для генерации изображения из текста. Без файлов."""
    prompt: str = Field(..., min_length=1, max_length=2000)
    negative_prompt: str = ""
    width: int = Field(1024, ge=256, le=4096)
    height: int = Field(1024, ge=256, le=4096)
    output_format: Literal["png", "webp", "jpg"] = "png"

class Txt2ImgOutput(BaseModel):
    image: OutputFile

@job_handler(
    slug="txt2img",
    name="Text to Image",
    description="Generates an image from a text prompt",
)
async def handle_txt2img(ctx: JobContext[Txt2ImgInput, Txt2ImgOutput]) -> Txt2ImgOutput:
    for provider in ctx.providers:
        try:
            result = await provider.execute(params=ctx.input.model_dump(exclude_none=True))
            return Txt2ImgOutput(
                image=OutputFile(
                    data=result.output_data,
                    content_type=f"image/{ctx.input.output_format}",
                )
            )
        except ProviderError as e:
            ctx.record_attempt(provider=provider, error=e)
            continue

    raise AllProvidersFailed()
```

### 9.4 Пример: image + text (image editing)

```python
class ImageEditInput(BaseModel):
    """Редактирование изображения по текстовому описанию."""
    image: Annotated[InputFile, FileConstraints(max_size_mb=20, formats=["png", "jpg"])]
    mask: Annotated[InputFile | None, FileConstraints(max_size_mb=20, formats=["png"])] = None
    prompt: str = Field(..., min_length=1, max_length=2000)
    strength: float = Field(0.7, ge=0.0, le=1.0)

class ImageEditOutput(BaseModel):
    image: OutputFile

@job_handler(
    slug="image_edit",
    name="Edit Image",
    description="Edits an image based on a text prompt and optional mask",
)
async def handle_image_edit(ctx: JobContext[ImageEditInput, ImageEditOutput]) -> ImageEditOutput:
    ...
```

### 9.5 JobContext

Контекст, передаваемый в handler-функцию:

```python
@dataclass
class JobContext(Generic[TInput, TOutput]):
    job_id: UUID                         # ID джоба
    input: TInput                        # Валидированная Pydantic-модель входных данных
                                         # (InputFile-поля уже резолвлены — содержат bytes)
    providers: list[ProviderAdapter]     # Провайдеры из fallback-цепочки (в порядке приоритета)
    user: UserInfo                        # Информация о пользователе (id, external_user_id)
    integration: IntegrationInfo          # Информация об интеграции
    language: str                         # Язык пользователя
    s3: S3Client                          # Клиент S3 (для промежуточных файлов)
    logger: Logger                        # Логгер с контекстом job_id

    def record_attempt(self, provider: ProviderAdapter, error: ProviderError) -> None:
        """Записать неудачную попытку для аудита (job_attempts)."""
        ...
```

### 9.6 Что делает декоратор `@job_handler`

Декоратор принимает только метаданные, не связанные с бизнес-логикой биллинга:

```python
def job_handler(
    slug: str,              # Уникальный идентификатор типа джоба
    name: str,              # Отображаемое название
    description: str = "",  # Описание для API-документации
):
```

**Что НЕ задаётся в декораторе** (настраивается в БД через админку):
- `credit_cost` — стоимость в кредитах
- `timeout_seconds` — таймаут выполнения
- `status` — active/disabled
- Fallback-цепочка провайдеров

**Что определяется моделями** (в коде, не в декораторе):
- Входные поля и их типы → `input_model` (Pydantic)
- Выходные поля → `output_model` (Pydantic)
- Валидация (форматы, размеры, диапазоны) → `FileConstraints` + Pydantic validators

### 9.7 Обработка InputFile / OutputFile фреймворком

**При создании джоба (API-слой):**
1. Партнёр отправляет JSON. Поля типа `InputFile` передаются как `file_id` (UUID)
2. Фреймворк валидирует: файл существует, принадлежит текущей интеграции, проходит `FileConstraints` (размер, формат)
3. Если валидация не пройдена → HTTP 400 `INVALID_INPUT`

**При выполнении джоба (воркер):**
1. Фреймворк загружает содержимое всех `InputFile`-полей из S3
2. Создаёт экземпляр `input_model` с резолвленными файлами
3. Вызывает handler-функцию
4. Получает `output_model` из handler'а
5. Загружает все `OutputFile`-поля в S3
6. Сохраняет ссылки на файлы результата в БД

### 9.8 Реестр и автообнаружение

При старте приложения:

1. Импортируются все модули из пакета `aimg/jobs/handlers/`
2. Декоратор `@job_handler` регистрирует каждый handler в глобальном реестре `JobRegistry`
3. CLI-команда `aimg sync-job-types` синхронизирует реестр с таблицей `job_types` в БД:
   - Новые handler'ы → создаёт записи с дефолтным `credit_cost=1` и `timeout_seconds=300`
   - Существующие → обновляет `name`, `description`, `input_schema`, `output_schema` (JSON Schema из Pydantic)
   - Отсутствующие в коде → НЕ удаляет (чтобы не потерять историю), только логирует warning
4. Воркер при получении задачи ищет handler по `job_type.slug` в реестре

### 9.9 Добавление нового типа джоба

1. Создать файл `aimg/jobs/handlers/my_new_job.py`
2. Определить `MyInput(BaseModel)` и `MyOutput(BaseModel)` с Pydantic-полями
3. Написать async-функцию с декоратором `@job_handler(slug="my_new_job", name="...", ...)`
4. Запустить `aimg sync-job-types` (или передеплоить — sync выполняется при старте)
5. В админке: задать `credit_cost` и `timeout_seconds`
6. В админке: настроить fallback-цепочку провайдеров
7. В админке: при необходимости ограничить доступ для конкретных интеграций

---

# Часть III. Модель данных

## 10. Схема базы данных

### partners

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK, DEFAULT gen_random_uuid() | |
| name | TEXT | NOT NULL | Название партнёра |
| status | TEXT | NOT NULL DEFAULT 'active' | `active` / `blocked` |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

### integrations

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| partner_id | UUID | FK → partners(id), NOT NULL | |
| name | TEXT | NOT NULL | Название интеграции |
| status | TEXT | NOT NULL DEFAULT 'active' | `active` / `blocked` |
| webhook_url | TEXT | NULL | URL для webhook-нотификаций |
| webhook_secret | TEXT | NULL | Секрет для HMAC-подписи webhook |
| rate_limit_rpm | INT | NOT NULL DEFAULT 60 | Лимит запросов в минуту |
| default_free_credits | INT | NOT NULL DEFAULT 10 | Бесплатные кредиты для новых пользователей |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**Индексы:** `idx_integrations_partner_id (partner_id)`

### api_keys

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| integration_id | UUID | FK → integrations(id), NOT NULL | |
| key_hash | TEXT | NOT NULL, UNIQUE | SHA-256 хэш JWT-токена |
| label | TEXT | NULL | Метка для идентификации ключа |
| is_revoked | BOOLEAN | NOT NULL DEFAULT false | |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| revoked_at | TIMESTAMPTZ | NULL | |

**Индексы:** `idx_api_keys_integration_id (integration_id)`, `idx_api_keys_key_hash (key_hash)`

### providers

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| slug | TEXT | NOT NULL, UNIQUE | `replicate`, `stability_ai`, `openai_dalle` |
| name | TEXT | NOT NULL | Отображаемое название |
| adapter_class | TEXT | NOT NULL | Python-путь к классу адаптера |
| base_url | TEXT | NULL | Базовый URL API провайдера |
| api_key_encrypted | TEXT | NOT NULL | Зашифрованный API-ключ провайдера |
| config | JSONB | NOT NULL DEFAULT '{}' | Дополнительные настройки провайдера |
| status | TEXT | NOT NULL DEFAULT 'active' | `active` / `disabled` |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

### job_types

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| slug | TEXT | NOT NULL, UNIQUE | `remove_bg`, `txt2img`, `upscale_2x` |
| name | TEXT | NOT NULL | Отображаемое название (синхронизируется из кода) |
| description | TEXT | NULL | Описание (синхронизируется из кода) |
| input_schema | JSONB | NOT NULL DEFAULT '{}' | JSON Schema входных данных (генерируется из Pydantic input_model) |
| output_schema | JSONB | NOT NULL DEFAULT '{}' | JSON Schema выходных данных (генерируется из Pydantic output_model) |
| credit_cost | INT | NOT NULL DEFAULT 1 | Стоимость в кредитах (**настраивается только в админке**) |
| timeout_seconds | INT | NOT NULL DEFAULT 300 | Таймаут (**настраивается только в админке**) |
| status | TEXT | NOT NULL DEFAULT 'active' | `active` / `disabled` (**настраивается только в админке**) |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

### job_type_providers

Связь тип джоба → провайдер с приоритетом (fallback-цепочка).

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| job_type_id | UUID | FK → job_types(id) | |
| provider_id | UUID | FK → providers(id) | |
| priority | INT | NOT NULL DEFAULT 0 | Меньше = пробуется первым |
| config_override | JSONB | NOT NULL DEFAULT '{}' | Переопределение конфига провайдера для этого типа |

**PK:** `(job_type_id, provider_id)`
**Индексы:** `idx_jtp_job_type_priority (job_type_id, priority)`

### integration_job_types

Контроль доступа: какие типы джобов доступны интеграции.

| Колонка | Тип | Ограничения |
|---|---|---|
| integration_id | UUID | FK → integrations(id) |
| job_type_id | UUID | FK → job_types(id) |

**PK:** `(integration_id, job_type_id)`

Если для интеграции нет записей в этой таблице — доступны все активные типы джобов.

### users

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| integration_id | UUID | FK → integrations(id), NOT NULL | |
| external_user_id | TEXT | NOT NULL | ID пользователя на стороне партнёра |
| free_credits | INT | NOT NULL DEFAULT 0 | Текущий баланс бесплатных кредитов |
| paid_credits | INT | NOT NULL DEFAULT 0 | Текущий баланс платных кредитов |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**UNIQUE:** `(integration_id, external_user_id)`
**Индексы:** `idx_users_integration_external (integration_id, external_user_id)`

### credit_transactions

Журнал всех операций с кредитами.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| user_id | UUID | FK → users(id), NOT NULL | |
| amount | INT | NOT NULL | Положительное = зачисление, отрицательное = списание |
| credit_type | TEXT | NOT NULL | `free` / `paid` |
| reason | TEXT | NOT NULL | `job_charge`, `topup`, `admin_adjustment`, `initial_grant`, `refund` |
| job_id | UUID | FK → jobs(id), NULL | Если операция связана с джобом |
| admin_user_id | UUID | NULL | Если операция выполнена администратором |
| comment | TEXT | NULL | Комментарий (обязателен для admin_adjustment) |
| balance_after | INT | NOT NULL | Баланс данного типа кредитов после операции |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**Индексы:** `idx_ct_user_id (user_id)`, `idx_ct_job_id (job_id)`, `idx_ct_created_at (created_at)`

### files

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| integration_id | UUID | FK → integrations(id), NOT NULL | |
| user_id | UUID | FK → users(id), NULL | |
| s3_bucket | TEXT | NOT NULL | |
| s3_key | TEXT | NOT NULL | |
| original_filename | TEXT | NULL | |
| content_type | TEXT | NOT NULL | MIME-тип |
| size_bytes | BIGINT | NOT NULL | |
| purpose | TEXT | NOT NULL | `input` / `output` |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**Индексы:** `idx_files_integration (integration_id)`

### jobs

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| integration_id | UUID | FK → integrations(id), NOT NULL | |
| user_id | UUID | FK → users(id), NOT NULL | |
| job_type_id | UUID | FK → job_types(id), NOT NULL | |
| status | TEXT | NOT NULL DEFAULT 'pending' | См. state machine |
| input_data | JSONB | NOT NULL | Входные данные (соответствует input_model). Файлы хранятся как file_id |
| output_data | JSONB | NULL | Выходные данные (соответствует output_model). NULL до завершения |
| provider_id | UUID | FK → providers(id), NULL | Провайдер, выполнивший задание |
| credit_charged | INT | NOT NULL DEFAULT 0 | Фактически списанные кредиты |
| error_code | TEXT | NULL | |
| error_message | TEXT | NULL | |
| provider_job_id | TEXT | NULL | ID задания на стороне провайдера |
| attempts | INT | NOT NULL DEFAULT 0 | Количество попыток |
| language | TEXT | NOT NULL DEFAULT 'en' | Язык сообщений об ошибках |
| idempotency_key | TEXT | NULL | |
| started_at | TIMESTAMPTZ | NULL | |
| completed_at | TIMESTAMPTZ | NULL | |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**Индексы:**
- `idx_jobs_integration_user (integration_id, user_id)`
- `idx_jobs_status (status) WHERE status IN ('pending', 'running')` (partial)
- `idx_jobs_created_at (created_at)`
- `idx_jobs_idempotency (integration_id, idempotency_key) WHERE idempotency_key IS NOT NULL` (partial, unique)

### job_attempts

Аудит каждой попытки выполнения через провайдера.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| job_id | UUID | FK → jobs(id), NOT NULL | |
| provider_id | UUID | FK → providers(id), NOT NULL | |
| attempt_number | INT | NOT NULL | |
| status | TEXT | NOT NULL | `success` / `failure` |
| error_code | TEXT | NULL | |
| error_message | TEXT | NULL | |
| duration_ms | INT | NULL | |
| started_at | TIMESTAMPTZ | NOT NULL | |
| completed_at | TIMESTAMPTZ | NULL | |

**Индексы:** `idx_ja_job_id (job_id)`

### admin_users

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| username | TEXT | NOT NULL, UNIQUE | |
| password_hash | TEXT | NOT NULL | bcrypt |
| role | TEXT | NOT NULL DEFAULT 'viewer' | `super_admin` / `admin` / `viewer` |
| status | TEXT | NOT NULL DEFAULT 'active' | `active` / `blocked` |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

### audit_log

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | BIGSERIAL | PK | |
| admin_user_id | UUID | FK → admin_users(id), NULL | |
| action | TEXT | NOT NULL | `partner.create`, `credits.adjust`, `api_key.revoke`, ... |
| entity_type | TEXT | NOT NULL | `partner`, `integration`, `user`, `job`, `api_key` |
| entity_id | UUID | NULL | |
| details | JSONB | NOT NULL DEFAULT '{}' | Детали изменения |
| ip_address | INET | NULL | |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**Индексы:** `idx_audit_entity (entity_type, entity_id)`, `idx_audit_created (created_at)`

### webhook_deliveries

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| integration_id | UUID | FK → integrations(id), NOT NULL | |
| job_id | UUID | FK → jobs(id), NOT NULL | |
| url | TEXT | NOT NULL | |
| payload | JSONB | NOT NULL | |
| status | TEXT | NOT NULL DEFAULT 'pending' | `pending` / `delivered` / `failed` |
| http_status | INT | NULL | Код ответа |
| attempt_count | INT | NOT NULL DEFAULT 0 | |
| max_attempts | INT | NOT NULL DEFAULT 3 | |
| next_retry_at | TIMESTAMPTZ | NULL | |
| last_error | TEXT | NULL | |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**Индексы:** `idx_wd_pending (status, next_retry_at) WHERE status = 'pending'`

---

## 11. Файловое хранилище

### 10.1 Структура S3-ключей

```
{bucket}/{partner_id}/{integration_id}/{job_id}/input/{original_filename}
{bucket}/{partner_id}/{integration_id}/{job_id}/output/{filename}
```

Для файлов, загруженных до создания джоба (через `POST /v1/files`):

```
{bucket}/{partner_id}/{integration_id}/uploads/{file_id}/{original_filename}
```

### 10.2 Доступ к файлам

- Скачивание результата: presigned URL с конфигурируемым TTL (по умолчанию 1 час)
- Прямой proxy-download не реализуется в v1
- Presigned URL генерируется при вызове `GET /v1/jobs/{job_id}/result`

---

# Часть IV. API спецификация

## 12. Принципы API

### Версионирование

Все партнёрские эндпоинты под префиксом `/v1/`. Админские — под `/admin/`.

### Формат ответа (envelope)

Все ответы обёрнуты в единую структуру:

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": true,
  "data": { ... },
  "error": null
}
```

При ошибке:

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": false,
  "data": null,
  "error": {
    "code": "INSUFFICIENT_CREDITS",
    "message": "Недостаточно кредитов. Требуется: 2, доступно: 0",
    "details": { "required": 2, "available": 0 }
  }
}
```

### Аутентификация

- Заголовок: `X-API-Key: <JWT-токен>`
- JWT содержит: `integration_id`, `partner_id`, `key_id`, `iat`
- Верификация: проверка подписи (HS256) + проверка отзыва в Redis

### Идентификация пользователя

- Заголовок: `X-External-User-Id: <строка>` — обязателен для user-scoped эндпоинтов
- Сервис разрешает пользователя по `(integration_id, external_user_id)`

### Пагинация

Cursor-based пагинация:
- Query-параметры: `?cursor=<opaque_string>&limit=<1-100>` (default limit = 20)
- В ответе: `next_cursor` (string | null), `has_more` (boolean)
- Курсор — base64-кодированная строка `created_at:id`

### Идемпотентность

- Заголовок: `Idempotency-Key: <строка>` — обязателен для мутирующих эндпоинтов (`POST`)
- Scope: per integration (один и тот же ключ у разных интеграций — разные операции)
- TTL: 24 часа (хранение в Redis с `SETEX`)
- Поведение: при повторе — возврат результата исходного запроса, HTTP 200

### Локализация

- Заголовок: `Accept-Language: ru` или query-параметр `?lang=ru`
- Поддерживаемые языки: `ru`, `en` (по умолчанию `en`)
- Влияет на: сообщения об ошибках, описания статусов
- Реализация: JSON-файлы ресурсов (`locales/ru.json`, `locales/en.json`)

---

## 13. Эндпоинты

### GET /health

Проверка работоспособности. Без авторизации.

**Response 200:**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "dependencies": {
    "database": "ok",
    "redis": "ok",
    "storage": "ok"
  }
}
```

---

### GET /v1/meta/languages

Список поддерживаемых языков. Без авторизации.

**Response 200:**
```json
{
  "request_id": "...",
  "success": true,
  "data": {
    "languages": [
      { "code": "en", "name": "English" },
      { "code": "ru", "name": "Русский" }
    ]
  }
}
```

---

### GET /v1/meta/job-types

Список доступных типов джобов для текущей интеграции.

**Headers:** `X-API-Key` (обязателен)

**Response 200:**
```json
{
  "request_id": "...",
  "success": true,
  "data": {
    "job_types": [
      {
        "slug": "remove_bg",
        "name": "Remove Background",
        "description": "Removes background from an image using AI",
        "credit_cost": 2,
        "timeout_seconds": 120,
        "input_schema": {
          "type": "object",
          "required": ["image"],
          "properties": {
            "image": {
              "type": "string",
              "format": "uuid",
              "description": "file_id загруженного изображения",
              "x-file-constraints": { "max_size_mb": 20, "formats": ["png", "jpg", "webp"] }
            },
            "output_format": {
              "type": "string",
              "enum": ["png", "webp"],
              "default": "png"
            }
          }
        },
        "output_schema": {
          "type": "object",
          "properties": {
            "image": { "type": "string", "format": "uuid", "description": "file_id результата" }
          }
        }
      },
      {
        "slug": "txt2img",
        "name": "Text to Image",
        "description": "Generates an image from a text prompt",
        "credit_cost": 5,
        "timeout_seconds": 180,
        "input_schema": {
          "type": "object",
          "required": ["prompt"],
          "properties": {
            "prompt": { "type": "string", "minLength": 1, "maxLength": 2000 },
            "negative_prompt": { "type": "string", "default": "" },
            "width": { "type": "integer", "minimum": 256, "maximum": 4096, "default": 1024 },
            "height": { "type": "integer", "minimum": 256, "maximum": 4096, "default": 1024 },
            "output_format": { "type": "string", "enum": ["png", "webp", "jpg"], "default": "png" }
          }
        },
        "output_schema": {
          "type": "object",
          "properties": {
            "image": { "type": "string", "format": "uuid" }
          }
        }
      }
    ]
  }
}
```

Партнёр использует `input_schema` чтобы понять, какие поля передавать в `POST /v1/jobs`. Поля с `format: "uuid"` и `x-file-constraints` — файлы, передаваемые как `file_id`.

---

### POST /v1/files

Загрузка файла для последующего использования в джобах.

**Headers:** `X-API-Key`, `X-External-User-Id`
**Content-Type:** `multipart/form-data`
**Body:** поле `file` — бинарное содержимое файла

**Response 201:**
```json
{
  "request_id": "...",
  "success": true,
  "data": {
    "file_id": "550e8400-e29b-41d4-a716-446655440000",
    "original_filename": "photo.jpg",
    "content_type": "image/jpeg",
    "size_bytes": 2048576
  }
}
```

**Ошибки:** `INVALID_FILE` (400), `UNAUTHORIZED` (401), `RATE_LIMITED` (429)

---

### POST /v1/jobs

Создать задание на обработку.

**Headers:** `X-API-Key`, `X-External-User-Id`, `Idempotency-Key` (обязателен)
**Content-Type:** `application/json`

**Request body:**

Единый формат для всех типов джобов. Поле `input` содержит данные, соответствующие `input_schema` выбранного `job_type`. Файловые поля передаются как `file_id` (UUID), полученные из `POST /v1/files`.

Пример (image job — remove_bg):
```json
{
  "job_type": "remove_bg",
  "input": {
    "image": "550e8400-e29b-41d4-a716-446655440000",
    "output_format": "png"
  },
  "language": "ru"
}
```

Пример (text job — txt2img):
```json
{
  "job_type": "txt2img",
  "input": {
    "prompt": "A sunset over mountains",
    "width": 1024,
    "height": 1024
  },
  "language": "en"
}
```

Пример (image + text — image_edit):
```json
{
  "job_type": "image_edit",
  "input": {
    "image": "550e8400-e29b-41d4-a716-446655440000",
    "mask": "660e8400-e29b-41d4-a716-446655440001",
    "prompt": "Replace the sky with a starry night",
    "strength": 0.8
  },
  "language": "en"
}
```

**Response 201 (джоб создан):**
```json
{
  "request_id": "...",
  "success": true,
  "data": {
    "job_id": "660e8400-e29b-41d4-a716-446655440001",
    "status": "pending",
    "job_type": "remove_bg",
    "credit_cost": 2,
    "created_at": "2026-02-21T12:00:00Z"
  }
}
```

**Response 200 (идемпотентный дубликат):**
Возвращает ранее созданный джоб в текущем его состоянии.

**Response 402 (недостаточно кредитов):**
```json
{
  "request_id": "...",
  "success": false,
  "data": null,
  "error": {
    "code": "INSUFFICIENT_CREDITS",
    "message": "Недостаточно кредитов. Требуется: 2, доступно: 0",
    "details": {
      "required": 2,
      "free_credits": 0,
      "paid_credits": 0
    }
  }
}
```

**Прочие ошибки:** `INVALID_INPUT` (400) — входные данные не прошли валидацию (несуществующий file_id, неверный формат файла, не пройдена Pydantic-валидация), `INVALID_JOB_TYPE` (400), `UNAUTHORIZED` (401), `JOB_TYPE_NOT_AVAILABLE` (403), `RATE_LIMITED` (429)

---

### GET /v1/jobs/{job_id}

Получить статус и данные джоба.

**Headers:** `X-API-Key`, `X-External-User-Id`

**Response 200:**
```json
{
  "request_id": "...",
  "success": true,
  "data": {
    "job_id": "660e8400-e29b-41d4-a716-446655440001",
    "status": "succeeded",
    "job_type": "remove_bg",
    "credit_charged": 2,
    "input": {
      "image": "550e8400-e29b-41d4-a716-446655440000",
      "output_format": "png"
    },
    "output": {
      "image": "770e8400-e29b-41d4-a716-446655440002"
    },
    "error": null,
    "created_at": "2026-02-21T12:00:00Z",
    "started_at": "2026-02-21T12:00:01Z",
    "completed_at": "2026-02-21T12:00:05Z"
  }
}
```

Поля `input` и `output` соответствуют `input_schema` и `output_schema` типа джоба. Файловые поля — `file_id` (UUID), по которым можно получить presigned URL через `GET /v1/files/{file_id}`.

При `failed`:
```json
{
  "data": {
    "job_id": "...",
    "status": "failed",
    "job_type": "remove_bg",
    "credit_charged": 0,
    "input": { "image": "550e8400-...", "output_format": "png" },
    "output": null,
    "error": {
      "code": "PROVIDER_ERROR",
      "message": "Ошибка обработки. Все провайдеры вернули ошибку."
    },
    "created_at": "2026-02-21T12:00:00Z",
    "started_at": "2026-02-21T12:00:01Z",
    "completed_at": "2026-02-21T12:00:10Z"
  }
}
```

**Ошибки:** `NOT_FOUND` (404), `UNAUTHORIZED` (401), `FORBIDDEN` (403)

---

### GET /v1/files/{file_id}

Получить presigned URL для скачивания файла (входного или результата). `file_id` берётся из `input` или `output` ответа `GET /v1/jobs/{id}`.

**Headers:** `X-API-Key`, `X-External-User-Id`

**Response 200:**
```json
{
  "request_id": "...",
  "success": true,
  "data": {
    "file_id": "770e8400-e29b-41d4-a716-446655440002",
    "download_url": "https://s3.example.com/...?X-Amz-Signature=...",
    "content_type": "image/png",
    "original_filename": "result.png",
    "size_bytes": 1048576,
    "expires_at": "2026-02-21T13:00:00Z"
  }
}
```

**Ошибки:** `NOT_FOUND` (404), `UNAUTHORIZED` (401), `FORBIDDEN` (403) — файл другой интеграции

---

### GET /v1/users/me/balance

Получить баланс текущего пользователя.

**Headers:** `X-API-Key`, `X-External-User-Id`

**Response 200:**
```json
{
  "request_id": "...",
  "success": true,
  "data": {
    "external_user_id": "user123",
    "free_credits": 3,
    "paid_credits": 47,
    "total_credits": 50
  }
}
```

---

### GET /v1/users/me/history

История джобов текущего пользователя.

**Headers:** `X-API-Key`, `X-External-User-Id`
**Query:** `?cursor=...&limit=20&status=succeeded&job_type=remove_bg`

**Response 200:**
```json
{
  "request_id": "...",
  "success": true,
  "data": {
    "jobs": [
      {
        "job_id": "660e8400-...",
        "status": "succeeded",
        "job_type": "remove_bg",
        "credit_charged": 2,
        "created_at": "2026-02-21T12:00:00Z",
        "completed_at": "2026-02-21T12:00:05Z"
      }
    ],
    "next_cursor": "MjAyNi0wMi0yMVQxMjowMDowMFo6NjYwZTg0MDA=",
    "has_more": true
  }
}
```

---

### POST /v1/billing/topup

Пополнить кредиты пользователя.

**Headers:** `X-API-Key`, `Idempotency-Key`
**Content-Type:** `application/json`

**Request body:**
```json
{
  "external_user_id": "user123",
  "amount": 100,
  "external_transaction_id": "stripe_pi_123456",
  "comment": "Покупка через Stripe"
}
```

`external_transaction_id` используется для идемпотентности пополнений (дополнительно к `Idempotency-Key`).

**Response 200:**
```json
{
  "request_id": "...",
  "success": true,
  "data": {
    "user_id": "880e8400-...",
    "external_user_id": "user123",
    "paid_credits": 147,
    "transaction_id": "990e8400-..."
  }
}
```

**Ошибки:** `INVALID_AMOUNT` (400), `UNAUTHORIZED` (401)

---

### POST /v1/billing/check

Проверить, хватает ли кредитов для типа джоба.

**Headers:** `X-API-Key`, `X-External-User-Id`
**Content-Type:** `application/json`

**Request body:**
```json
{
  "job_type": "remove_bg"
}
```

**Response 200:**
```json
{
  "request_id": "...",
  "success": true,
  "data": {
    "can_afford": true,
    "credit_cost": 2,
    "free_credits": 3,
    "paid_credits": 47,
    "total_credits": 50
  }
}
```

---

### Админские эндпоинты (prefix: /admin/)

Аутентификация: session-based (cookie). Не используют API-ключи.

#### Аутентификация

| Метод | Путь | Описание |
|---|---|---|
| POST | /admin/auth/login | Вход (username + password → session cookie) |
| POST | /admin/auth/logout | Выход |
| GET | /admin/auth/me | Текущий пользователь |

#### Партнёры

| Метод | Путь | Описание | Роль |
|---|---|---|---|
| GET | /admin/partners | Список партнёров (пагинация) | viewer+ |
| POST | /admin/partners | Создать партнёра | admin+ |
| GET | /admin/partners/{id} | Детали партнёра | viewer+ |
| PATCH | /admin/partners/{id} | Обновить партнёра (name, status) | admin+ |

#### Интеграции

| Метод | Путь | Описание | Роль |
|---|---|---|---|
| GET | /admin/partners/{id}/integrations | Интеграции партнёра | viewer+ |
| POST | /admin/partners/{id}/integrations | Создать интеграцию | admin+ |
| GET | /admin/integrations/{id} | Детали интеграции | viewer+ |
| PATCH | /admin/integrations/{id} | Обновить интеграцию | admin+ |

#### API-ключи

| Метод | Путь | Описание | Роль |
|---|---|---|---|
| GET | /admin/integrations/{id}/api-keys | Список ключей интеграции | viewer+ |
| POST | /admin/integrations/{id}/api-keys | Сгенерировать новый ключ | admin+ |
| DELETE | /admin/api-keys/{id} | Отозвать ключ | admin+ |

При генерации ключа (`POST`) ответ содержит сам JWT-токен **один раз**. После этого он не может быть прочитан повторно (хранится только хэш).

#### Пользователи

| Метод | Путь | Описание | Роль |
|---|---|---|---|
| GET | /admin/users | Поиск (query: external_user_id, integration_id) | viewer+ |
| GET | /admin/users/{id} | Детали + баланс + последние джобы | viewer+ |
| POST | /admin/users/{id}/credits | Корректировка кредитов | admin+ |

**POST /admin/users/{id}/credits:**
```json
{
  "amount": 50,
  "credit_type": "paid",
  "comment": "Компенсация за сбой 2026-02-20"
}
```
`comment` — обязательное поле. Отрицательный `amount` для списания (баланс не может стать < 0).

#### Джобы

| Метод | Путь | Описание | Роль |
|---|---|---|---|
| GET | /admin/jobs | Поиск/фильтрация (date_from, date_to, status, partner_id, integration_id, user_id, job_type) | viewer+ |
| GET | /admin/jobs/{id} | Полные детали + attempts | viewer+ |

#### Типы джобов и провайдеры

| Метод | Путь | Описание | Роль |
|---|---|---|---|
| GET | /admin/job-types | Список типов джобов | viewer+ |
| POST | /admin/job-types | Создать тип | super_admin |
| PATCH | /admin/job-types/{id} | Обновить тип | super_admin |
| GET | /admin/providers | Список провайдеров | viewer+ |
| POST | /admin/providers | Создать провайдера | super_admin |
| PATCH | /admin/providers/{id} | Обновить провайдера | super_admin |

#### Аудит и экспорт

| Метод | Путь | Описание | Роль |
|---|---|---|---|
| GET | /admin/audit-log | Журнал действий (пагинация, фильтры) | viewer+ |
| GET | /admin/export/jobs | Экспорт джобов в CSV/JSON (query: format=csv/json + фильтры) | admin+ |
| GET | /admin/dashboard/stats | Статистика: активные джобы, джобы/день, расход кредитов, процент ошибок | viewer+ |

---

## 14. Обработка ошибок

### Коды ошибок

| Код | HTTP | Описание |
|---|---|---|
| `INVALID_FILE` | 400 | Неверный формат, размер превышен, файл повреждён (при загрузке через `POST /v1/files`) |
| `INVALID_INPUT` | 400 | Входные данные джоба не прошли валидацию (несуществующий file_id, нарушение FileConstraints, ошибка Pydantic-валидации). Детали в `error.details` |
| `INVALID_JOB_TYPE` | 400 | Неизвестный slug типа джоба |
| `INVALID_AMOUNT` | 400 | Некорректная сумма пополнения (≤ 0) |
| `UNAUTHORIZED` | 401 | Отсутствует, невалидный или отозванный API-ключ |
| `FORBIDDEN` | 403 | Доступ к ресурсу чужого партнёра / интеграции |
| `JOB_TYPE_NOT_AVAILABLE` | 403 | Интеграция не имеет доступа к данному типу джоба |
| `INSUFFICIENT_CREDITS` | 402 | Недостаточно кредитов для создания джоба |
| `NOT_FOUND` | 404 | Джоб, пользователь или файл не найден |
| `JOB_NOT_COMPLETED` | 409 | Попытка скачать результат незавершённого джоба |
| `RATE_LIMITED` | 429 | Превышен лимит запросов |
| `PROVIDER_ERROR` | 502 | Ошибка провайдера после исчерпания всех попыток fallback |
| `TIMEOUT` | 504 | Обработка превысила `timeout_seconds` |
| `INTERNAL` | 500 | Непредвиденная ошибка сервиса |

### Локализация ошибок

Сообщения ошибок возвращаются на языке, указанном в `Accept-Language` или `?lang=`. Файлы локализации содержат маппинг `error_code → message_template`.

### Retry guidance

Ответы с ошибками содержат заголовок `Retry-After` (в секундах) для кодов 429 и 503.

---

## 15. Webhooks

### Конфигурация

Webhook-URL и секрет задаются per integration через админку (поля `webhook_url`, `webhook_secret` в таблице `integrations`).

### Payload

```json
{
  "event": "job.completed",
  "job_id": "660e8400-...",
  "status": "succeeded",
  "job_type": "remove_bg",
  "created_at": "2026-02-21T12:00:00Z",
  "completed_at": "2026-02-21T12:00:05Z"
}
```

Для `failed`:
```json
{
  "event": "job.completed",
  "job_id": "660e8400-...",
  "status": "failed",
  "job_type": "remove_bg",
  "error": {
    "code": "PROVIDER_ERROR",
    "message": "All providers failed"
  },
  "created_at": "2026-02-21T12:00:00Z",
  "completed_at": "2026-02-21T12:00:10Z"
}
```

### Подпись

Заголовок `X-AIMG-Signature` содержит HMAC-SHA256 подпись тела запроса с использованием `webhook_secret` интеграции.

```
X-AIMG-Signature: sha256=<hex-digest>
```

Партнёр верифицирует подпись для защиты от подделки.

### Retry-политика

- Максимум 3 попытки
- Интервалы: 10 секунд, 60 секунд, 300 секунд (exponential backoff)
- Успех: HTTP 2xx от партнёра
- Статус доставки отслеживается в `webhook_deliveries`

---

# Часть V. Бизнес-логика

## 16. State machine джобов

### Состояния

| Состояние | Описание |
|---|---|
| `pending` | Джоб создан, кредиты зарезервированы. Ожидает подхвата воркером. |
| `running` | Воркер выполняет задание через провайдера. |
| `succeeded` | Провайдер вернул успешный результат. Файл сохранён. Кредиты подтверждены. |
| `failed` | Все попытки исчерпаны или неустранимая ошибка. Кредиты возвращены. |
| `cancelled` | Зарезервировано для будущей отмены (v2). |

### Переходы

```
[POST /v1/jobs]
      │
      ▼
  Проверка кредитов ──(недостаточно)──► HTTP 402 (джоб НЕ создаётся)
      │
   (достаточно)
      │
  Резервирование кредитов (PG-транзакция)
      │
      ▼
  ┌─────────┐
  │ pending  │ ──── LPUSH в Redis-очередь
  └────┬─────┘
       │
       │ Воркер: BRPOP из очереди
       ▼
  ┌─────────┐
  │ running  │
  └────┬─────┘
       │
  ┌────┴────┐
  │         │
  ▼         ▼
Провайдер  Провайдер
 успех      ошибка
  │         │
  │    ┌────┴──────┐
  │    │ Есть ещё   │──(да)──► Следующий провайдер (остаёмся в running)
  │    │ провайдеры?│
  │    └────┬──────┘
  │         │(нет)
  ▼         ▼
┌──────────┐  ┌────────┐
│succeeded │  │ failed │
└──────────┘  └────────┘
     │              │
  Подтвердить    Вернуть
  кредиты        кредиты
     │              │
  Сохранить      Записать
  результат      ошибку
     │              │
  Webhook        Webhook
  (если есть)    (если есть)
```

### Side-effects по переходам

| Переход | Действия |
|---|---|
| → `pending` | INSERT jobs, INSERT credit_transactions (reserve), LPUSH в Redis, INSERT idempotency key |
| `pending` → `running` | UPDATE jobs.status, UPDATE jobs.started_at, set provider_id |
| `running` → `running` (fallback) | INSERT job_attempts (failure), INCREMENT attempts, set next provider_id |
| `running` → `succeeded` | INSERT job_attempts (success), upload result → S3, UPDATE output_data (JSONB с file_id), UPDATE completed_at, fire webhook |
| `running` → `failed` | INSERT job_attempts (failure), INSERT credit_transactions (refund), UPDATE users balances, UPDATE error_code/message, UPDATE completed_at, fire webhook |

---

## 17. Биллинг и кредиты

### Принцип: транзакционный журнал — source of truth

Таблица `credit_transactions` является единственным источником истины о балансах. Поля `users.free_credits` и `users.paid_credits` — денормализованный кэш для быстрого чтения. Истинный баланс всегда можно вычислить:

```sql
SELECT
  COALESCE(SUM(amount) FILTER (WHERE credit_type = 'free'), 0) AS free_credits,
  COALESCE(SUM(amount) FILTER (WHERE credit_type = 'paid'), 0) AS paid_credits
FROM credit_transactions
WHERE user_id = :user_id;
```

Все операции с кредитами (списание, возврат, пополнение, корректировка) выполняются в одной PostgreSQL-транзакции: запись в `credit_transactions` + обновление кэша в `users`.

### Типы кредитов и порядок списания

1. **Free credits** — начисляются при автосоздании пользователя. Количество определяется `integration.default_free_credits`. Списываются первыми.
2. **Paid credits** — добавляются через `POST /v1/billing/topup` или администратором. Списываются после исчерпания free credits.

### Двухфазное резервирование

Для предотвращения race condition (пользователь запускает несколько джобов параллельно, суммарная стоимость превышает баланс):

1. **Резервирование** (при создании джоба): кредиты списываются сразу. Пользователь видит уменьшенный баланс.
2. **Подтверждение** (при `succeeded`): резервирование становится окончательным. Дополнительных действий с балансом не требуется.
3. **Возврат** (при `failed`): зарезервированные кредиты возвращаются на баланс.

### Flow создания джоба (биллинг)

```
1. Получить credit_cost из job_types по slug
2. Вычислить split:
   free_deduction = min(credit_cost, user.free_credits)
   paid_deduction = credit_cost - free_deduction
3. В одной PostgreSQL-транзакции:
   a. UPDATE users SET
        free_credits = free_credits - free_deduction,
        paid_credits = paid_credits - paid_deduction
      WHERE id = :user_id
        AND free_credits >= :free_deduction
        AND paid_credits >= :paid_deduction
   b. Если UPDATE затронул 0 строк → concurrent race, HTTP 402
   c. INSERT credit_transactions (reason='job_charge', amount отрицательный)
   d. INSERT jobs (status='pending', credit_charged=credit_cost)
   e. COMMIT
4. LPUSH задачи в Redis-очередь (вне транзакции)
   Если crash между COMMIT и LPUSH — orphaned job recovery подхватит (см. ниже)
```

### Flow возврата кредитов (при failure)

```
1. Определить исходные списания из credit_transactions WHERE job_id = :job_id
2. В одной PostgreSQL-транзакции:
   a. INSERT credit_transactions (reason='refund', amount положительный)
   b. UPDATE users SET
        free_credits = free_credits + free_refund,
        paid_credits = paid_credits + paid_refund
   c. UPDATE jobs SET status='failed', error_code=..., completed_at=now()
   d. COMMIT
```

### Flow пополнения

```
1. Проверить идемпотентность (Idempotency-Key + external_transaction_id)
2. В одной PostgreSQL-транзакции:
   a. INSERT credit_transactions (reason='topup', amount положительный)
   b. UPDATE users SET paid_credits = paid_credits + :amount
   c. COMMIT
```

### Инвариант

Баланс пользователя (`free_credits`, `paid_credits`) никогда не может стать отрицательным. Гарантируется условием `WHERE free_credits >= :deduction AND paid_credits >= :deduction` в UPDATE.

### Механизмы защиты от потери данных

#### 1. Атомарность операций

Каждое изменение баланса — одна PostgreSQL-транзакция. Невозможна ситуация, когда `credit_transactions` обновлена, а `users` — нет (или наоборот).

#### 2. Recovery janitor (восстановление зависших джобов)

Периодический процесс (запускается в воркере каждые `AIMG_WORKER_RECOVERY_INTERVAL` секунд):

```
1. Найти джобы в status='running' дольше чем (timeout_seconds + 60s grace):
   SELECT * FROM jobs
   WHERE status = 'running'
     AND started_at < now() - (timeout_seconds + interval '60 seconds')
2. Для каждого: пометить как failed, вернуть кредиты (атомарная транзакция)
3. Логировать как recovery event
```

#### 3. Orphaned job recovery (потерянные при enqueue)

При старте воркера:

```
1. Найти джобы в status='pending' старше 60 секунд, которых нет в Redis-очереди:
   SELECT * FROM jobs WHERE status = 'pending' AND created_at < now() - interval '60 seconds'
2. Для каждого: повторно LPUSH в Redis-очередь
3. Логировать как orphaned recovery event
```

#### 4. Reconciliation (сверка балансов)

CLI-команда `aimg reconcile-balances`:

```
1. Для каждого пользователя:
   a. Вычислить expected_free = SUM(amount) FROM credit_transactions WHERE credit_type='free'
   b. Вычислить expected_paid = SUM(amount) FROM credit_transactions WHERE credit_type='paid'
   c. Если users.free_credits != expected_free ИЛИ users.paid_credits != expected_paid:
      - Логировать расхождение
      - С флагом --fix: UPDATE users SET free_credits=expected_free, paid_credits=expected_paid
2. Рекомендуется запускать по cron ежедневно (или при подозрении на сбой)
```

---

## 18. Rate limiting

### Уровни

| Уровень | Метрика | Хранение | Конфигурация |
|---|---|---|---|
| Per-integration | Запросов в минуту (RPM) | Redis (sliding window counter) | `integrations.rate_limit_rpm` |
| Per-user | Джобов в час | Redis (sliding window counter) | Глобальная env-переменная `AIMG_USER_RATE_LIMIT_JOBS_PER_HOUR` (default: 60) |

### Заголовки в ответе

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1708531200
```

При превышении лимита: HTTP 429 с заголовком `Retry-After`.

---

## 19. Идемпотентность

### Механизм

- Ключ хранится в Redis: `aimg:idempotency:{integration_id}:{key}` → `{job_id}`
- TTL: 24 часа (SETEX)
- При повторном запросе с тем же ключом: загружается существующий джоб из PostgreSQL, возвращается HTTP 200

### Поведение при повторе

| Состояние исходного запроса | Действие при повторе |
|---|---|
| Джоб создан (любой статус) | Вернуть текущее состояние джоба, HTTP 200 |
| Ключ существует, но job_id не найден | Удалить ключ, обработать как новый запрос |

---

# Часть VI. Админ-панель

## 20. Спецификация админ-панели

### Технологический стек

- **Starlette** — ASGI-фреймворк (HTTP routing, middleware, sessions)
- **Jinja2** — серверный рендеринг HTML-шаблонов
- **htmx** — динамическая интерактивность без JS-фреймворка (AJAX-подгрузка фрагментов, inline-редактирование, живой поиск, пагинация без перезагрузки)
- **Pico CSS** (или аналог) — минимальный classless CSS-фреймворк для приемлемого внешнего вида без дизайнера
- **asyncpg** — тот же драйвер PostgreSQL, что и в API-сервере
- Общие repository-классы и Pydantic-модели переиспользуются из основного кода

Админка — **отдельный процесс**, не встроенный в FastAPI. Запускается как третья точка входа Docker-образа (`admin`). Подключается к тем же PostgreSQL и Redis.

### Аутентификация

- Отдельная от партнёрской (не API-ключи)
- Username + password → session cookie (HttpOnly, Secure, SameSite=Strict)
- Хранение: `admin_users` таблица, bcrypt для паролей
- Session хранится в Redis (prefix `aimg:admin_session:`)

### Роли

| Роль | Права |
|---|---|
| `super_admin` | Полный доступ: всё от admin + управление типами джобов, провайдерами, admin_users |
| `admin` | Управление партнёрами, интеграциями, ключами, пользователями, кредитами. Просмотр джобов и аудита. Экспорт. |
| `viewer` | Только просмотр: партнёры, интеграции, пользователи, джобы, аудит, dashboard. Без изменений. |

### Разделы

1. **Dashboard** — активные джобы, джобы/день (график), расход кредитов, % ошибок
2. **Партнёры** — CRUD, статус (active/blocked)
3. **Интеграции** — CRUD, webhook-настройки, генерация/отзыв ключей
4. **Пользователи** — поиск, просмотр баланса и истории, корректировка кредитов
5. **Джобы** — таблица с фильтрами (дата, статус, партнёр, интеграция, тип, user_id), детали с попытками и ссылками на файлы
6. **Типы джобов** — CRUD (super_admin), настройка fallback-цепочки
7. **Провайдеры** — CRUD (super_admin)
8. **Аудит** — журнал действий с фильтрами
9. **Экспорт** — выгрузка джобов: CSV (обязательно), JSON (опционально)

### Паттерны htmx

Основные паттерны, используемые в админке:

- **Списки с пагинацией:** `hx-get="/admin/jobs?page=2"` подгружает следующую страницу в таблицу
- **Живой поиск:** `hx-get="/admin/users?q=..."` с `hx-trigger="keyup changed delay:300ms"`
- **Фильтры:** изменение select/checkbox → `hx-get` с текущими параметрами фильтра
- **Inline-формы:** корректировка кредитов, изменение статуса — без перезагрузки
- **Подтверждение:** `hx-confirm="Отозвать ключ?"` для опасных действий

### Аудит

Все мутирующие действия в админке записываются в `audit_log`: кто, когда, что изменил, с какого IP. Обязательно логируются:
- Создание/блокировка партнёров
- Генерация/отзыв API-ключей
- Корректировка кредитов (с комментарием)
- Изменение типов джобов и провайдеров

---

# Часть VII. Операции

## 21. Нефункциональные требования

### Производительность

- API response time (p95): < 200ms (исключая выполнение джоба)
- Throughput: 100 RPS на единственном инстансе (v1)
- Job execution: зависит от провайдера, ожидание 5-120 секунд

### Доступность

- v1: single-instance, допускается downtime при обновлении
- Graceful shutdown: воркер завершает текущий джоб перед остановкой

### Observability

- Формат логов: структурированный JSON
- Каждый запрос получает `request_id` (UUID), пробрасывается во все операции
- Каждый джоб отслеживается по `job_id`
- Health endpoint (`GET /health`) проверяет подключение к PostgreSQL, Redis и S3

### Безопасность

- API-ключи: JWT с HS256, кэш отзыва в Redis
- Изоляция данных: партнёр не может получить данные другого партнёра
- Input sanitization: валидация всех входных данных через Pydantic
- SQL injection: параметризованные запросы через asyncpg
- Провайдерские ключи: хранятся зашифрованными (`providers.api_key_encrypted`)

---

## 22. Развёртывание и конфигурация

### Docker

- Единый Docker image содержит API, воркер и админку
- Точка входа определяется аргументом: `api`, `worker` или `admin`
- docker-compose для локальной разработки:

```yaml
services:
  api:
    image: aimg
    command: api
    ports: ["8000:8000"]
  worker:
    image: aimg
    command: worker
  admin:
    image: aimg
    command: admin
    ports: ["8001:8001"]
  postgres:
    image: postgres:16
  redis:
    image: redis:7-alpine
  minio:
    image: minio/minio
```

### Переменные окружения

| Переменная | Описание | Default |
|---|---|---|
| `AIMG_DATABASE_URL` | URL подключения к PostgreSQL | `postgresql://aimg:aimg@localhost:5432/aimg` |
| `AIMG_REDIS_URL` | URL подключения к Redis | `redis://localhost:6379/0` |
| `AIMG_S3_ENDPOINT` | Endpoint S3 (MinIO) | `http://localhost:9000` |
| `AIMG_S3_ACCESS_KEY` | S3 access key | — |
| `AIMG_S3_SECRET_KEY` | S3 secret key | — |
| `AIMG_S3_BUCKET` | Имя bucket | `aimg` |
| `AIMG_S3_PRESIGN_TTL` | TTL presigned URL в секундах | `3600` |
| `AIMG_JWT_SECRET` | Секрет для подписи JWT API-ключей | — (обязателен) |
| `AIMG_ENCRYPTION_KEY` | Ключ шифрования провайдерских API-ключей | — (обязателен) |
| `AIMG_WORKER_CONCURRENCY` | Количество параллельных задач воркера | `5` |
| `AIMG_WORKER_RECOVERY_INTERVAL` | Интервал проверки зависших задач (секунды) | `60` |
| `AIMG_USER_RATE_LIMIT_JOBS_PER_HOUR` | Лимит джобов на пользователя в час | `60` |
| `AIMG_DEFAULT_LANGUAGE` | Язык по умолчанию | `en` |
| `AIMG_LOG_LEVEL` | Уровень логирования | `INFO` |
| `AIMG_ADMIN_SESSION_SECRET` | Секрет для подписи session cookie админки | — (обязателен) |
| `AIMG_ADMIN_PORT` | Порт админ-панели | `8001` |

### Миграции

- Инструмент: Alembic
- Команда: `alembic upgrade head`
- Миграции запускаются перед стартом приложения (в entrypoint или init-контейнере)

### OpenAPI

Документация доступна по `/docs` (Swagger UI) и `/openapi.json`.

---

## 23. Локализация (i18n)

### Реализация

- JSON-файлы: `locales/en.json`, `locales/ru.json`
- Структура: маппинг `error_code → message_template` с поддержкой placeholder'ов

```json
{
  "INSUFFICIENT_CREDITS": "Недостаточно кредитов. Требуется: {required}, доступно: {available}",
  "INVALID_FILE": "Файл не подходит: {reason}",
  "PROVIDER_ERROR": "Ошибка обработки. Попробуйте позже."
}
```

### Выбор языка

1. Заголовок `Accept-Language: ru`
2. Query-параметр `?lang=ru`
3. Поле `language` в теле запроса `POST /v1/jobs`
4. Fallback: `AIMG_DEFAULT_LANGUAGE` (env)

Приоритет: поле в теле → query → заголовок → default.

### Добавление нового языка

Добавить файл `locales/{code}.json` и зарегистрировать в `GET /v1/meta/languages`. Изменение бизнес-логики не требуется.

---

## 24. Критерии приёмки

### Основной flow

1. Партнёр загружает файл через `POST /v1/files` — получает `file_id`
2. Партнёр создаёт джоб через `POST /v1/jobs` — получает `job_id`, статус `pending`
3. Партнёр опрашивает `GET /v1/jobs/{id}` — статус переходит в `running`, затем в `succeeded`
4. Партнёр скачивает результат через `GET /v1/jobs/{id}/result` — получает presigned URL

### Биллинг

5. При создании джоба кредиты резервируются (баланс уменьшается)
6. При `succeeded` — кредиты подтверждены (баланс не меняется)
7. При `failed` — кредиты возвращены (баланс увеличивается)
8. При недостатке кредитов — HTTP 402, джоб не создаётся, баланс не меняется
9. Баланс не может стать отрицательным
10. `POST /v1/billing/topup` увеличивает paid_credits

### Идемпотентность

11. Повторный запрос `POST /v1/jobs` с тем же `Idempotency-Key` возвращает ранее созданный джоб
12. Повторное списание кредитов не происходит

### Fallback

13. При ошибке первого провайдера — попытка следующего в цепочке
14. При исчерпании всех провайдеров — статус `failed`

### Webhooks

15. При `succeeded` / `failed` — POST на `webhook_url` (если настроен)
16. Подпись проверяема через `X-AIMG-Signature`
17. При недоступности партнёра — retry (3 попытки с backoff)

### Админка

18. Создание партнёра и интеграции через админку
19. Генерация и отзыв API-ключей
20. Просмотр джобов с фильтрами и деталями
21. Корректировка кредитов пользователя (с обязательным комментарием)
22. Экспорт истории джобов в CSV
23. Все действия записываются в audit log

### Rate limiting

24. При превышении лимита — HTTP 429 с `Retry-After`

### Локализация

25. Сообщения об ошибках возвращаются на языке, указанном в запросе
26. RU и EN поддерживаются из коробки
