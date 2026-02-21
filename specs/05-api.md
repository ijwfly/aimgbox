# Часть IV. API спецификация

> Связанные документы: [Схема БД](04-database-schema.md) · [Job Handlers](03-job-handlers.md) · [Бизнес-логика](06-business-logic.md) · [Индекс](README.md)

---

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
