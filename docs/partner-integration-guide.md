# AIMG API — Руководство по интеграции для партнёров

## Содержание

- [Обзор](#обзор)
- [Аутентификация](#аутентификация)
- [Формат ответов](#формат-ответов)
- [Коды ошибок](#коды-ошибок)
- [Rate Limiting](#rate-limiting)
- [Идемпотентность](#идемпотентность)
- [Локализация](#локализация)
- [Эндпоинты](#эндпоинты)
  - [Health Check](#health-check)
  - [Типы задач](#типы-задач)
  - [Загрузка файлов](#загрузка-файлов)
  - [Скачивание файлов](#скачивание-файлов)
  - [Создание задачи](#создание-задачи)
  - [Получение статуса задачи](#получение-статуса-задачи)
  - [Получение результата](#получение-результата)
  - [Баланс пользователя](#баланс-пользователя)
  - [Пополнение баланса](#пополнение-баланса)
  - [Проверка достаточности средств](#проверка-достаточности-средств)
  - [История задач](#история-задач)
- [Вебхуки](#вебхуки)
- [Типичные сценарии](#типичные-сценарии)
  - [Генерация изображения по текстовому описанию](#сценарий-1-генерация-изображения-по-текстовому-описанию)
  - [Удаление фона с фотографии](#сценарий-2-удаление-фона-с-фотографии)
  - [Пополнение баланса и обработка платежей](#сценарий-3-пополнение-баланса-и-обработка-платежей)
  - [Интеграция с вебхуками (без поллинга)](#сценарий-4-интеграция-с-вебхуками-без-поллинга)
- [Рекомендации](#рекомендации)

---

## Обзор

AIMG — REST API для обработки изображений с помощью ИИ.

**Основные возможности:**

- Генерация изображений по текстовому описанию (text-to-image)
- Редактирование изображений (image-to-image)
- Удаление фона с изображений (remove background)
- Кредитная система биллинга с двухфазным списанием
- Идемпотентность для безопасных повторных запросов
- Локализация ошибок (en, ru)

---

## Аутентификация

Каждый запрос к API (кроме `GET /health`) требует два заголовка:

| Заголовок | Описание |
|-----------|----------|
| `X-API-Key` | JWT-токен, выданный при создании интеграции |
| `X-External-User-Id` | Идентификатор конечного пользователя в вашей системе |

`X-API-Key` — это JWT (HS256), содержащий `integration_id`, `partner_id` и `key_id`. Вы получаете его от администратора AIMG при подключении.

`X-External-User-Id` — произвольная строка, идентифицирующая пользователя в вашей системе. AIMG автоматически создаёт внутреннюю запись пользователя при первом обращении с новым `X-External-User-Id`.

```bash
curl -X GET https://api.example.com/v1/users/me/balance \
  -H "X-API-Key: eyJhbGciOiJIUzI1NiIs..." \
  -H "X-External-User-Id: user-42"
```

---

## Формат ответов

Все эндпоинты `/v1/*` возвращают ответы в унифицированном контейнере:

### Успешный ответ

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": true,
  "data": { ... },
  "error": null
}
```

### Ответ с ошибкой

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": false,
  "data": null,
  "error": {
    "code": "INSUFFICIENT_CREDITS",
    "message": "Недостаточно кредитов",
    "details": {
      "required": 10,
      "available": 3
    }
  }
}
```

Каждый ответ содержит заголовок `X-Request-ID`. Вы можете передать свой `X-Request-ID` в запросе — иначе он будет сгенерирован автоматически. Сохраняйте `request_id` для обращения в поддержку.

> **Исключение:** `GET /health` возвращает ответ напрямую, без контейнера.

---

## Коды ошибок

| Код | HTTP-статус | Описание |
|-----|-------------|----------|
| `UNAUTHORIZED` | 401 | Невалидный, отозванный или отсутствующий API-ключ |
| `FORBIDDEN` | 403 | Доступ запрещён (ресурс принадлежит другой интеграции) |
| `NOT_FOUND` | 404 | Ресурс не найден |
| `INVALID_INPUT` | 400 | Некорректные входные данные |
| `INVALID_FILE` | 400 | Невалидный файл (слишком большой, пустой) |
| `INVALID_JOB_TYPE` | 400 | Неизвестный или неактивный тип задачи |
| `INSUFFICIENT_CREDITS` | 402 | Недостаточно кредитов |
| `RATE_LIMITED` | 429 | Превышен лимит запросов |
| `INVALID_AMOUNT` | 400 | Некорректная сумма (при пополнении) |
| `INTERNAL` | 500 | Внутренняя ошибка сервера |

---

## Rate Limiting

API применяет два уровня ограничений:

### 1. Лимит запросов интеграции (RPM)

Ограничение на количество запросов в минуту для всей интеграции. Текущий лимит передаётся в заголовках ответа:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1709481600
```

### 2. Лимит задач пользователя

Ограничение на количество создаваемых задач на одного пользователя в час. Проверяется при вызове `POST /v1/jobs`.

При превышении любого лимита API возвращает `429` с заголовком `Retry-After` (в секундах):

```
HTTP/1.1 429 Too Many Requests
Retry-After: 30
```

---

## Идемпотентность

Для защиты от дублирования операций при сетевых сбоях поддерживается заголовок `Idempotency-Key`:

```bash
curl -X POST https://api.example.com/v1/jobs \
  -H "X-API-Key: eyJ..." \
  -H "X-External-User-Id: user-42" \
  -H "Idempotency-Key: order-12345-job-1" \
  -H "Content-Type: application/json" \
  -d '{"job_type": "txt2img", "input": {"prompt": "a cat"}}'
```

- Поддерживается в `POST /v1/jobs` и `POST /v1/billing/topup`
- Повторный запрос с тем же ключом возвращает кешированный результат (HTTP 200 вместо 201)
- Ключ действует 24 часа
- Пополнение баланса дополнительно защищено полем `external_transaction_id` на уровне базы данных

---

## Локализация

Сообщения об ошибках можно получать на разных языках. Поддерживаются: `en`, `ru`.

Способы указания языка (по приоритету):
1. Параметр `?lang=ru` в URL
2. Заголовок `Accept-Language: ru`
3. Поле `language` при создании задачи
4. По умолчанию: `en`

```bash
# Через заголовок
curl -H "Accept-Language: ru" ...

# Через query-параметр
curl "https://api.example.com/v1/jobs?lang=ru" ...
```

---

## Эндпоинты

### Health Check

Проверка доступности сервиса. Не требует аутентификации.

```
GET /health
```

```bash
curl https://api.example.com/health
```

**Ответ (200):**

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

`status` — `"ok"` если все зависимости доступны, `"degraded"` если хотя бы одна недоступна.

---

### Типы задач

Список доступных типов обработки. Возвращает JSON-схемы входных и выходных данных.

```
GET /v1/meta/job-types
```

```bash
curl https://api.example.com/v1/meta/job-types \
  -H "X-API-Key: eyJ..."
```

> Этот эндпоинт требует только `X-API-Key` (без `X-External-User-Id`).

**Ответ (200):**

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
        "credit_cost": 5,
        "timeout_seconds": 120,
        "input_schema": { ... },
        "output_schema": { ... }
      },
      {
        "slug": "txt2img",
        "name": "Text to Image",
        "description": "Generates an image from a text prompt using AI",
        "credit_cost": 10,
        "timeout_seconds": 300,
        "input_schema": { ... },
        "output_schema": { ... }
      }
    ]
  }
}
```

Рекомендуем кешировать этот ответ на стороне клиента — типы задач меняются редко.

---

### Загрузка файлов

Загрузка файла для последующего использования во входных данных задачи.

```
POST /v1/files
```

```bash
curl -X POST https://api.example.com/v1/files \
  -H "X-API-Key: eyJ..." \
  -H "X-External-User-Id: user-42" \
  -F "file=@photo.png"
```

**Ограничения:**
- Максимальный размер файла: **50 МБ**
- Пустые файлы отклоняются

**Ответ (201):**

```json
{
  "request_id": "...",
  "success": true,
  "data": {
    "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "original_filename": "photo.png",
    "content_type": "image/png",
    "size_bytes": 1024000
  }
}
```

Сохраните `file_id` — он понадобится при создании задач, требующих входное изображение.

---

### Скачивание файлов

Получение временной ссылки на скачивание файла.

```
GET /v1/files/{file_id}
```

```bash
curl https://api.example.com/v1/files/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "X-API-Key: eyJ..." \
  -H "X-External-User-Id: user-42"
```

**Ответ (200):**

```json
{
  "request_id": "...",
  "success": true,
  "data": {
    "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "download_url": "https://storage.example.com/...?signature=...",
    "content_type": "image/png",
    "original_filename": "photo.png",
    "size_bytes": 1024000,
    "expires_at": "2026-03-03T13:00:00"
  }
}
```

`download_url` — предподписанная ссылка с ограниченным сроком действия (`expires_at`).

---

### Создание задачи

```
POST /v1/jobs
```

```bash
curl -X POST https://api.example.com/v1/jobs \
  -H "X-API-Key: eyJ..." \
  -H "X-External-User-Id: user-42" \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "txt2img",
    "input": {
      "prompt": "a beautiful sunset over mountains"
    },
    "language": "ru"
  }'
```

**Поля запроса:**

| Поле | Тип | Обязательное | Описание |
|------|-----|-------------|----------|
| `job_type` | string | Да | Slug типа задачи (из `GET /v1/meta/job-types`) |
| `input` | object | Да | Входные данные согласно `input_schema` типа задачи |
| `language` | string | Нет | Язык ошибок (`en`, `ru`). По умолчанию: `en` |

**Ответ (201):**

```json
{
  "request_id": "...",
  "success": true,
  "data": {
    "job_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "status": "pending",
    "job_type": "txt2img",
    "credit_cost": 10,
    "input": {
      "prompt": "a beautiful sunset over mountains"
    },
    "output": null,
    "error": null,
    "created_at": "2026-03-03T12:00:00",
    "started_at": null,
    "completed_at": null
  }
}
```

При создании задачи кредиты **резервируются** (но не списываются окончательно). Если задача завершится ошибкой — кредиты будут возвращены.

---

### Получение статуса задачи

```
GET /v1/jobs/{job_id}
```

```bash
curl https://api.example.com/v1/jobs/f47ac10b-58cc-4372-a567-0e02b2c3d479 \
  -H "X-API-Key: eyJ..." \
  -H "X-External-User-Id: user-42"
```

**Ответ (200):**

```json
{
  "request_id": "...",
  "success": true,
  "data": {
    "job_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "status": "succeeded",
    "job_type": "txt2img",
    "credit_cost": 10,
    "input": { "prompt": "a beautiful sunset over mountains" },
    "output": {
      "image": "b2c3d479-f47a-c10b-58cc-437200000001"
    },
    "error": null,
    "created_at": "2026-03-03T12:00:00",
    "started_at": "2026-03-03T12:00:03",
    "completed_at": "2026-03-03T12:00:25"
  }
}
```

**Жизненный цикл задачи:**

```
pending → running → succeeded
                  → failed
```

| Статус | Описание | `output` | `error` |
|--------|----------|----------|---------|
| `pending` | В очереди, ожидает обработки | `null` | `null` |
| `running` | Обрабатывается | `null` | `null` |
| `succeeded` | Успешно завершена | `{...}` | `null` |
| `failed` | Ошибка при обработке | `null` | `{code, message}` |

---

### Получение результата

Скачивание результата выполненной задачи. Работает только для задач со статусом `succeeded`.

```
GET /v1/jobs/{job_id}/result
```

```bash
curl https://api.example.com/v1/jobs/f47ac10b-58cc-4372-a567-0e02b2c3d479/result \
  -H "X-API-Key: eyJ..." \
  -H "X-External-User-Id: user-42"
```

**Ответ (200):**

```json
{
  "request_id": "...",
  "success": true,
  "data": {
    "job_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "file_id": "b2c3d479-f47a-c10b-58cc-437200000001",
    "download_url": "https://storage.example.com/...?signature=...",
    "content_type": "image/png",
    "size_bytes": 2048000,
    "expires_at": "2026-03-03T13:00:00"
  }
}
```

**Ошибки:**
- `400 INVALID_INPUT` — задача ещё не завершена (проверьте `status`)
- `404 NOT_FOUND` — задача не найдена или выходной файл отсутствует

---

### Баланс пользователя

```
GET /v1/users/me/balance
```

```bash
curl https://api.example.com/v1/users/me/balance \
  -H "X-API-Key: eyJ..." \
  -H "X-External-User-Id: user-42"
```

**Ответ (200):**

```json
{
  "request_id": "...",
  "success": true,
  "data": {
    "external_user_id": "user-42",
    "free_credits": 100,
    "paid_credits": 50,
    "total_credits": 150
  }
}
```

- `free_credits` — бесплатные кредиты (начисляются при регистрации, невозвратные)
- `paid_credits` — оплаченные кредиты (пополнение через `POST /v1/billing/topup`)
- При списании сначала расходуются `free_credits`, затем `paid_credits`

---

### Пополнение баланса

Начисление оплаченных кредитов пользователю. Вызывается из вашего бэкенда после подтверждения оплаты.

```
POST /v1/billing/topup
```

```bash
curl -X POST https://api.example.com/v1/billing/topup \
  -H "X-API-Key: eyJ..." \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: payment-98765" \
  -d '{
    "external_user_id": "user-42",
    "amount": 100,
    "external_transaction_id": "txn_stripe_pi_3abc",
    "comment": "Оплата через Stripe"
  }'
```

> Этот эндпоинт требует только `X-API-Key` (без `X-External-User-Id` в заголовке). Пользователь указывается в теле запроса.

**Поля запроса:**

| Поле | Тип | Обязательное | Описание |
|------|-----|-------------|----------|
| `external_user_id` | string | Да | ID пользователя в вашей системе |
| `amount` | integer | Да | Количество кредитов (> 0) |
| `external_transaction_id` | string | Да | ID транзакции в вашей платёжной системе |
| `comment` | string | Нет | Комментарий (виден в админке) |

**Ответ (201):**

```json
{
  "request_id": "...",
  "success": true,
  "data": {
    "user_id": "internal-uuid",
    "external_user_id": "user-42",
    "paid_credits": 150,
    "transaction_id": "internal-txn-uuid"
  }
}
```

**Защита от дублирования:** если `external_transaction_id` уже использовался для этого пользователя, API вернёт существующий результат (без повторного начисления).

---

### Проверка достаточности средств

Проверка, хватит ли кредитов у пользователя для задачи заданного типа.

```
POST /v1/billing/check
```

```bash
curl -X POST https://api.example.com/v1/billing/check \
  -H "X-API-Key: eyJ..." \
  -H "X-External-User-Id: user-42" \
  -H "Content-Type: application/json" \
  -d '{"job_type": "txt2img"}'
```

**Ответ (200):**

```json
{
  "request_id": "...",
  "success": true,
  "data": {
    "can_afford": true,
    "credit_cost": 10,
    "free_credits": 100,
    "paid_credits": 50,
    "total_credits": 150
  }
}
```

---

### История задач

Получение списка задач пользователя с пагинацией.

```
GET /v1/users/me/history
```

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|----------|
| `cursor` | string | — | Курсор для следующей страницы |
| `limit` | integer | 20 | Элементов на странице (1–100) |
| `status` | string | — | Фильтр по статусу (`pending`, `running`, `succeeded`, `failed`) |
| `job_type` | string | — | Фильтр по типу задачи (slug) |

```bash
curl "https://api.example.com/v1/users/me/history?limit=10&status=succeeded" \
  -H "X-API-Key: eyJ..." \
  -H "X-External-User-Id: user-42"
```

**Ответ (200):**

```json
{
  "request_id": "...",
  "success": true,
  "data": {
    "jobs": [
      {
        "job_id": "f47ac10b-...",
        "status": "succeeded",
        "job_type": "txt2img",
        "credit_charged": 10,
        "created_at": "2026-03-03T12:00:00",
        "completed_at": "2026-03-03T12:00:25"
      }
    ],
    "next_cursor": "MjAyNi0wMy0wM1QxMjowMDowMHxmNDdhYzEwYi0...",
    "has_more": true
  }
}
```

Для получения следующей страницы передайте `next_cursor` в параметр `cursor`. Повторяйте, пока `has_more` не станет `false`.

---

## Вебхуки

Вебхуки позволяют получать уведомления об изменении статуса задач без необходимости поллинга. URL и секрет для подписи настраиваются в админке при создании интеграции.

### Формат доставки

**Метод:** `POST`

**Заголовки:**

```
Content-Type: application/json
X-AIMG-Signature: sha256=5d5b09f6dcb2d53a5fffc60c4ac0d55fabdf556069d6631545f42aa6e3500f2e
```

**Тело:**

```json
{
  "event": "job.succeeded",
  "job_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "succeeded",
  "job_type": "txt2img",
  "created_at": "2026-03-03T12:00:00",
  "completed_at": "2026-03-03T12:00:25",
  "error": null
}
```

При ошибке:

```json
{
  "event": "job.failed",
  "job_id": "f47ac10b-...",
  "status": "failed",
  "job_type": "txt2img",
  "created_at": "2026-03-03T12:00:00",
  "completed_at": "2026-03-03T12:00:10",
  "error": {
    "code": "PROVIDER_ERROR",
    "message": "All providers failed"
  }
}
```

### Типы событий

| Событие | Когда срабатывает |
|---------|-------------------|
| `job.pending` | Задача поставлена в очередь |
| `job.running` | Задача начала обрабатываться |
| `job.succeeded` | Задача успешно выполнена |
| `job.failed` | Задача завершилась с ошибкой |

### Проверка подписи

Каждый вебхук подписан HMAC-SHA256. **Обязательно** проверяйте подпись перед обработкой.

**Python:**

```python
import hmac
import hashlib

def verify_webhook(payload_bytes: bytes, signature: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(
        secret.encode(),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)

# Использование в обработчике
signature = request.headers["X-AIMG-Signature"]
body = await request.body()

if not verify_webhook(body, signature, WEBHOOK_SECRET):
    return Response(status_code=401)
```

**Node.js:**

```javascript
const crypto = require('crypto');

function verifyWebhook(payloadBuffer, signature, secret) {
  const expected = 'sha256=' + crypto
    .createHmac('sha256', secret)
    .update(payloadBuffer)
    .digest('hex');
  return crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(expected)
  );
}
```

### Политика повторных попыток

Если ваш сервер не ответил `2xx`, доставка будет повторена:

| Попытка | Задержка |
|---------|----------|
| 1-я | Немедленно |
| 2-я | Через 10 секунд |
| 3-я | Через 60 секунд |
| 4-я | Через 300 секунд |

После 4-й неуспешной попытки доставка прекращается. Отвечайте на вебхуки быстро (таймаут — 10 секунд).

---

## Типичные сценарии

### Сценарий 1: Генерация изображения по текстовому описанию

Полный цикл: проверка баланса → создание задачи → поллинг → скачивание результата.

```bash
# 1. Проверить баланс
curl -s https://api.example.com/v1/users/me/balance \
  -H "X-API-Key: $API_KEY" \
  -H "X-External-User-Id: user-42"
# → total_credits: 150

# 2. Проверить, хватает ли средств
curl -s -X POST https://api.example.com/v1/billing/check \
  -H "X-API-Key: $API_KEY" \
  -H "X-External-User-Id: user-42" \
  -H "Content-Type: application/json" \
  -d '{"job_type": "txt2img"}'
# → can_afford: true, credit_cost: 10

# 3. Создать задачу (с ключом идемпотентности)
curl -s -X POST https://api.example.com/v1/jobs \
  -H "X-API-Key: $API_KEY" \
  -H "X-External-User-Id: user-42" \
  -H "Idempotency-Key: req-$(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "txt2img",
    "input": {
      "prompt": "a beautiful sunset over mountains, oil painting style",
      "negative_prompt": "blurry, low quality",
      "width": 1024,
      "height": 1024,
      "output_format": "png"
    }
  }'
# → job_id: "f47ac10b-...", status: "pending"

# 4. Поллинг статуса (каждые 2 секунды)
while true; do
  RESPONSE=$(curl -s https://api.example.com/v1/jobs/f47ac10b-... \
    -H "X-API-Key: $API_KEY" \
    -H "X-External-User-Id: user-42")

  STATUS=$(echo $RESPONSE | jq -r '.data.status')

  case $STATUS in
    "succeeded")
      echo "Задача выполнена!"
      break
      ;;
    "failed")
      echo "Ошибка: $(echo $RESPONSE | jq -r '.data.error')"
      exit 1
      ;;
    *)
      echo "Статус: $STATUS, ожидание..."
      sleep 2
      ;;
  esac
done

# 5. Скачать результат
curl -s https://api.example.com/v1/jobs/f47ac10b-.../result \
  -H "X-API-Key: $API_KEY" \
  -H "X-External-User-Id: user-42"
# → download_url: "https://storage.example.com/...?signature=..."

# 6. Скачать файл по ссылке
curl -o result.png "$(echo $RESULT | jq -r '.data.download_url')"
```

---

### Сценарий 2: Удаление фона с фотографии

Требует предварительной загрузки файла.

```bash
# 1. Загрузить изображение
UPLOAD=$(curl -s -X POST https://api.example.com/v1/files \
  -H "X-API-Key: $API_KEY" \
  -H "X-External-User-Id: user-42" \
  -F "file=@portrait.jpg")

FILE_ID=$(echo $UPLOAD | jq -r '.data.file_id')
echo "Файл загружен: $FILE_ID"

# 2. Создать задачу на удаление фона
JOB=$(curl -s -X POST https://api.example.com/v1/jobs \
  -H "X-API-Key: $API_KEY" \
  -H "X-External-User-Id: user-42" \
  -H "Content-Type: application/json" \
  -d "{
    \"job_type\": \"remove_bg\",
    \"input\": {
      \"image\": \"$FILE_ID\",
      \"output_format\": \"png\"
    }
  }")

JOB_ID=$(echo $JOB | jq -r '.data.job_id')
echo "Задача создана: $JOB_ID"

# 3. Ожидание результата (поллинг)
while true; do
  STATUS=$(curl -s https://api.example.com/v1/jobs/$JOB_ID \
    -H "X-API-Key: $API_KEY" \
    -H "X-External-User-Id: user-42" | jq -r '.data.status')

  if [ "$STATUS" = "succeeded" ]; then
    break
  elif [ "$STATUS" = "failed" ]; then
    echo "Ошибка при обработке"
    exit 1
  fi
  sleep 2
done

# 4. Скачать результат
RESULT=$(curl -s https://api.example.com/v1/jobs/$JOB_ID/result \
  -H "X-API-Key: $API_KEY" \
  -H "X-External-User-Id: user-42")

curl -o portrait_no_bg.png "$(echo $RESULT | jq -r '.data.download_url')"
echo "Результат сохранён: portrait_no_bg.png"
```

---

### Сценарий 3: Пополнение баланса и обработка платежей

Типичная серверная интеграция: ваш бэкенд получает подтверждение оплаты и начисляет кредиты.

```bash
# Пополнить баланс после подтверждения оплаты
# ВАЖНО: используйте Idempotency-Key и external_transaction_id
# для защиты от двойного начисления
curl -s -X POST https://api.example.com/v1/billing/topup \
  -H "X-API-Key: $API_KEY" \
  -H "Idempotency-Key: stripe-pi-3N2abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "external_user_id": "user-42",
    "amount": 500,
    "external_transaction_id": "stripe_pi_3N2abc123",
    "comment": "Покупка пакета 500 кредитов"
  }'
# → paid_credits: 500, transaction_id: "..."

# Повторный вызов с тем же external_transaction_id
# безопасен — вернёт существующий результат без двойного начисления
```

---

### Сценарий 4: Интеграция с вебхуками (без поллинга)

Рекомендуемый подход для production — вместо поллинга используйте вебхуки.

**Ваш сервер (Python/FastAPI):**

```python
import hmac
import hashlib
import httpx
from fastapi import FastAPI, Request, Response

app = FastAPI()
WEBHOOK_SECRET = "your-webhook-secret"
API_KEY = "eyJ..."
API_BASE = "https://api.example.com"

@app.post("/webhooks/aimg")
async def handle_aimg_webhook(request: Request):
    # 1. Проверить подпись
    body = await request.body()
    signature = request.headers.get("X-AIMG-Signature", "")
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        return Response(status_code=401)

    # 2. Обработать событие
    payload = await request.json()
    event = payload["event"]
    job_id = payload["job_id"]

    if event == "job.succeeded":
        # 3. Скачать результат
        async with httpx.AsyncClient() as client:
            result = await client.get(
                f"{API_BASE}/v1/jobs/{job_id}/result",
                headers={
                    "X-API-Key": API_KEY,
                    "X-External-User-Id": "user-42",
                },
            )
            download_url = result.json()["data"]["download_url"]
            # ... сохранить или отправить пользователю

    elif event == "job.failed":
        error = payload.get("error", {})
        # ... уведомить пользователя об ошибке
        # Кредиты возвращены автоматически

    return Response(status_code=200)
```

---

## Рекомендации

### Обработка ошибок

1. **Проверяйте `success`** в контейнере ответа перед использованием `data`
2. **Реагируйте на `429`** — используйте значение из заголовка `Retry-After`
3. **Для `5xx`** — повторяйте с экспоненциальной задержкой (1с, 2с, 4с, 8с)
4. **Сохраняйте `request_id`** — он необходим для диагностики проблем в поддержке

### Работа с кредитами

1. **Двухфазное списание:** кредиты резервируются при создании задачи, подтверждаются при успехе, возвращаются при ошибке
2. **Проверяйте баланс** через `POST /v1/billing/check` перед созданием задачи, чтобы показать пользователю понятное сообщение
3. **Всегда указывайте `external_transaction_id`** при пополнении — это гарантирует идемпотентность на уровне базы данных

### Надёжность

1. **Используйте `Idempotency-Key`** для всех POST-запросов, чтобы безопасно повторять запросы при сбоях
2. **Настройте вебхуки** вместо поллинга для production-систем
3. **Верифицируйте подписи вебхуков** — не доверяйте данным без проверки `X-AIMG-Signature`
4. **Отвечайте на вебхуки быстро** (< 10с), при необходимости обрабатывайте асинхронно

### Производительность

1. **Кешируйте типы задач** — результат `GET /v1/meta/job-types` меняется редко
2. **Переиспользуйте HTTP-соединения** — используйте пул/сессии в HTTP-клиенте
3. **Поллинг с задержкой** — начинайте с 1–2с, увеличивайте до 5с; не опрашивайте чаще 1 раза в секунду
