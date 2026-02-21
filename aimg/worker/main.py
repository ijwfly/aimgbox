import asyncio
import signal

import structlog

from aimg.common.connections import create_db_pool, create_redis_client, create_s3_client
from aimg.common.logging import configure_logging
from aimg.common.settings import Settings

logger = structlog.get_logger()


async def run_worker() -> None:
    settings = Settings()
    configure_logging(settings.log_level)

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

    async with create_s3_client(settings):
        while not shutdown_event.is_set():
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=1.0)
            except TimeoutError:
                pass

    await db_pool.close()
    await redis_client.aclose()
    logger.info("worker_stopped")


def main() -> None:
    asyncio.run(run_worker())
