# Часть III. Модель данных

> Связанные документы: [Бизнес-логика](06-business-logic.md) · [API](05-api.md) · [Индекс](README.md)

---

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

### 11.1 Структура S3-ключей

```
{bucket}/{partner_id}/{integration_id}/{job_id}/input/{original_filename}
{bucket}/{partner_id}/{integration_id}/{job_id}/output/{filename}
```

Для файлов, загруженных до создания джоба (через `POST /v1/files`):

```
{bucket}/{partner_id}/{integration_id}/uploads/{file_id}/{original_filename}
```

### 11.2 Доступ к файлам

- Скачивание результата: presigned URL с конфигурируемым TTL (по умолчанию 1 час)
- Прямой proxy-download не реализуется в v1
- Presigned URL генерируется при вызове `GET /v1/jobs/{job_id}/result`
