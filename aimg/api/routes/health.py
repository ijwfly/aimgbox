import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends

from aimg import __version__
from aimg.api.dependencies import get_db_pool, get_redis, get_s3_client, get_settings
from aimg.common.health import check_database, check_redis, check_storage
from aimg.common.settings import Settings

router = APIRouter()


@router.get("/health")
async def health(
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    redis_client: aioredis.Redis = Depends(get_redis),
    s3_client: object = Depends(get_s3_client),
    settings: Settings = Depends(get_settings),
) -> dict:
    db_status = await check_database(db_pool)
    redis_status = await check_redis(redis_client)
    storage_status = await check_storage(s3_client, settings.s3_bucket)

    statuses = [db_status, redis_status, storage_status]
    overall = "ok" if all(s == "ok" for s in statuses) else "degraded"

    return {
        "status": overall,
        "version": __version__,
        "dependencies": {
            "database": db_status,
            "redis": redis_status,
            "storage": storage_status,
        },
    }
