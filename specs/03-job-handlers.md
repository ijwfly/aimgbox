# Реализация джобов (Job Handlers)

> Связанные документы: [Архитектура](02-architecture.md) · [Схема БД](04-database-schema.md) · [Индекс](README.md)

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
