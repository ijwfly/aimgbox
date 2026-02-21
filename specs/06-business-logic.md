# Часть V. Бизнес-логика

> Связанные документы: [Схема БД](04-database-schema.md) · [API](05-api.md) · [Архитектура](02-architecture.md) · [Индекс](README.md)

---

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
