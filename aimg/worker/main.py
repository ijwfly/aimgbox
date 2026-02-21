import asyncio
import signal
from datetime import UTC, datetime
from uuid import UUID

import structlog

from aimg.common.connections import create_db_pool, create_redis_client, create_s3_client
from aimg.common.encryption import decrypt_value
from aimg.common.logging import configure_logging
from aimg.common.settings import Settings
from aimg.db.repos.files import FileRepo
from aimg.db.repos.job_attempts import JobAttemptRepo
from aimg.db.repos.job_types import JobTypeRepo
from aimg.db.repos.jobs import JobRepo
from aimg.db.repos.providers import ProviderRepo
from aimg.jobs.context import JobContext
from aimg.jobs.fields import InputFile, OutputFile
from aimg.jobs.registry import JobRegistry, discover_handlers
from aimg.providers.base import AllProvidersFailedError, ProviderAdapter
from aimg.providers.failing_mock import FailingMockProvider
from aimg.providers.mock import MockProvider
from aimg.providers.replicate import ReplicateAdapter
from aimg.services.billing import refund_credits

logger = structlog.get_logger()

QUEUE_KEY = "aimg:jobs:queue"

PROVIDER_ADAPTERS: dict[str, type[ProviderAdapter]] = {
    "aimg.providers.mock.MockProvider": MockProvider,
    "aimg.providers.replicate.ReplicateAdapter": ReplicateAdapter,
    "aimg.providers.failing_mock.FailingMockProvider": FailingMockProvider,
}


async def process_job(
    job_id: UUID,
    db_pool,
    redis_client,
    s3_client,
    settings: Settings,
) -> None:
    job_repo = JobRepo(db_pool)
    jt_repo = JobTypeRepo(db_pool)
    provider_repo = ProviderRepo(db_pool)
    file_repo = FileRepo(db_pool)
    attempt_repo = JobAttemptRepo(db_pool)
    log = logger.bind(job_id=str(job_id))

    job = await job_repo.get_by_id(job_id)
    if not job:
        log.error("job_not_found")
        return

    if job.status != "pending":
        log.warning("job_not_pending", status=job.status)
        return

    job_type = await jt_repo.get_by_id(job.job_type_id)
    if not job_type:
        log.error("job_type_not_found")
        await _fail_job(db_pool, job_repo, job, "INTERNAL", "Job type not found")
        return

    handler_info = JobRegistry.get(job_type.slug)
    if not handler_info:
        log.error("handler_not_found", slug=job_type.slug)
        await _fail_job(
            db_pool, job_repo, job, "INTERNAL", f"No handler for {job_type.slug}"
        )
        return

    # Load provider chain
    jt_providers = await jt_repo.get_providers_for_job_type(job_type.id)
    if not jt_providers:
        log.error("no_providers_configured")
        await _fail_job(db_pool, job_repo, job, "INTERNAL", "No providers configured")
        return

    adapters: list[ProviderAdapter] = []
    provider_ids: list[UUID] = []
    for jtp in jt_providers:
        prov = await provider_repo.get_by_id(jtp.provider_id)
        if not prov or prov.status != "active":
            continue
        adapter_cls = PROVIDER_ADAPTERS.get(prov.adapter_class)
        if not adapter_cls:
            log.warning("unknown_adapter_class", adapter_class=prov.adapter_class)
            continue
        merged_config = {**prov.config, **jtp.config_override}
        if prov.api_key_encrypted and prov.api_key_encrypted != "not-needed":
            try:
                merged_config["api_key"] = decrypt_value(
                    prov.api_key_encrypted, settings.encryption_key
                )
            except Exception:
                log.warning(
                    "provider_key_decrypt_failed", provider_id=str(prov.id)
                )
                continue
        adapters.append(adapter_cls(provider_id=prov.id, config=merged_config))
        provider_ids.append(prov.id)

    if not adapters:
        log.error("no_active_adapters")
        await _fail_job(db_pool, job_repo, job, "INTERNAL", "No active providers")
        return

    # Update status to running
    await job_repo.update_status(job.id, "running", provider_id=provider_ids[0])
    log.info("job_running")

    # Resolve InputFile fields: download from S3
    input_data = dict(job.input_data)
    if handler_info.input_model:
        for field_name in handler_info.input_model.model_fields:
            val = input_data.get(field_name)
            if val and isinstance(val, str):
                try:
                    file_id = UUID(val)
                except ValueError:
                    continue
                file_record = await file_repo.get_by_id(file_id)
                if file_record:
                    resp = await s3_client.get_object(
                        Bucket=file_record.s3_bucket, Key=file_record.s3_key
                    )
                    body_bytes = await resp["Body"].read()
                    input_data[field_name] = InputFile(
                        file_id=file_id,
                        data=body_bytes,
                        content_type=file_record.content_type,
                        original_filename=file_record.original_filename,
                        size_bytes=file_record.size_bytes,
                    )

    # Build typed input model
    try:
        typed_input = handler_info.input_model(**input_data)
    except Exception as e:
        log.error("input_model_build_failed", error=str(e))
        await _fail_job(db_pool, job_repo, job, "INVALID_INPUT", str(e))
        return

    ctx = JobContext(
        job_id=job.id,
        input=typed_input,
        providers=adapters,
        language=job.language,
        logger=log,
    )

    # Execute handler
    try:
        result = await handler_info.handler_fn(ctx)
    except AllProvidersFailedError:
        log.error("all_providers_failed")
        for i, attempt in enumerate(ctx._attempts):
            await attempt_repo.create(
                job_id=job.id,
                provider_id=attempt.provider_id,
                attempt_number=i + 1,
                status="failure",
                started_at=datetime.now(UTC),
                error_code=attempt.error_code,
                error_message=attempt.error_message,
                completed_at=datetime.now(UTC),
            )
        await _fail_job(
            db_pool, job_repo, job, "PROVIDER_ERROR", "All providers failed"
        )
        return
    except Exception as e:
        log.exception("handler_error")
        await _fail_job(db_pool, job_repo, job, "INTERNAL", str(e))
        return

    # Upload OutputFile fields to S3 and create file records
    output_data = {}
    if result and handler_info.output_model:
        for field_name in handler_info.output_model.model_fields:
            val = getattr(result, field_name, None)
            if isinstance(val, OutputFile):
                ext = val.content_type.rsplit("/", 1)[-1] if "/" in val.content_type else "bin"
                filename = val.filename or f"output.{ext}"
                s3_key = f"{job.integration_id}/{job.id}/output/{filename}"
                await s3_client.put_object(
                    Bucket=settings.s3_bucket,
                    Key=s3_key,
                    Body=val.data,
                    ContentType=val.content_type,
                )
                out_file = await file_repo.create(
                    integration_id=job.integration_id,
                    user_id=job.user_id,
                    s3_bucket=settings.s3_bucket,
                    s3_key=s3_key,
                    content_type=val.content_type,
                    size_bytes=len(val.data),
                    purpose="output",
                    original_filename=filename,
                )
                output_data[field_name] = str(out_file.id)
            else:
                output_data[field_name] = val

    # Record success attempt
    if provider_ids:
        await attempt_repo.create(
            job_id=job.id,
            provider_id=provider_ids[0],
            attempt_number=1,
            status="success",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )

    # Mark succeeded
    await job_repo.update_status(
        job.id,
        "succeeded",
        output_data=output_data,
        provider_id=provider_ids[0],
    )
    log.info("job_succeeded")


async def _fail_job(
    db_pool, job_repo: JobRepo, job, error_code: str, error_message: str
) -> None:
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await refund_credits(db_pool, conn, job.id, job.user_id)
            await job_repo.update_status(
                job.id,
                "failed",
                error_code=error_code,
                error_message=error_message,
                conn=conn,
            )


async def run_worker() -> None:
    settings = Settings()
    configure_logging(settings.log_level)

    discover_handlers()
    logger.info("handlers_discovered", count=len(JobRegistry.all()))

    db_pool = await create_db_pool(settings)
    redis_client = create_redis_client(settings)

    shutdown_event = asyncio.Event()

    def handle_signal() -> None:
        logger.info("worker_shutdown_requested")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    logger.info("worker_started", concurrency=settings.worker_concurrency)

    async with create_s3_client(settings) as s3_client:
        # Auto-create bucket for dev
        try:
            await s3_client.head_bucket(Bucket=settings.s3_bucket)
        except Exception:
            await s3_client.create_bucket(Bucket=settings.s3_bucket)

        while not shutdown_event.is_set():
            try:
                result = await redis_client.brpop(QUEUE_KEY, timeout=1)
                if result is None:
                    continue
                _, job_id_str = result
                job_id = UUID(job_id_str)
                logger.info("job_dequeued", job_id=job_id_str)
                await process_job(job_id, db_pool, redis_client, s3_client, settings)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("worker_loop_error")
                await asyncio.sleep(1)

    await db_pool.close()
    await redis_client.aclose()
    logger.info("worker_stopped")


def main() -> None:
    asyncio.run(run_worker())
