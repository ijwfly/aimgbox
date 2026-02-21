from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from aimg.api.middleware import RequestIdMiddleware
from aimg.api.routes.health import router as health_router
from aimg.common.connections import create_db_pool, create_redis_client, create_s3_client
from aimg.common.logging import configure_logging
from aimg.common.settings import Settings

logger = structlog.get_logger()


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()

    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator:
        app.state.settings = settings

        # Database pool
        app.state.db_pool = await create_db_pool(settings)
        logger.info("database_pool_created")

        # Redis
        app.state.redis = create_redis_client(settings)
        logger.info("redis_client_created")

        # S3
        s3_cm = create_s3_client(settings)
        app.state.s3_client = await s3_cm.__aenter__()
        app.state._s3_cm = s3_cm
        logger.info("s3_client_created")

        # Auto-create bucket for dev
        try:
            await app.state.s3_client.head_bucket(Bucket=settings.s3_bucket)
        except Exception:
            await app.state.s3_client.create_bucket(Bucket=settings.s3_bucket)
            logger.info("s3_bucket_created", bucket=settings.s3_bucket)

        logger.info("app_started")
        yield

        # Shutdown
        await app.state.db_pool.close()
        logger.info("database_pool_closed")

        await app.state.redis.aclose()
        logger.info("redis_client_closed")

        await app.state._s3_cm.__aexit__(None, None, None)
        logger.info("s3_client_closed")

        logger.info("app_stopped")

    app = FastAPI(title="AIMG API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health_router)

    return app
