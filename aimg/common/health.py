import asyncpg
import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger()


async def check_database(pool: asyncpg.Pool) -> str:
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return "ok"
    except Exception:
        logger.exception("database_health_check_failed")
        return "error"


async def check_redis(client: aioredis.Redis) -> str:
    try:
        await client.ping()
        return "ok"
    except Exception:
        logger.exception("redis_health_check_failed")
        return "error"


async def check_storage(s3_client: object, bucket: str) -> str:
    try:
        await s3_client.head_bucket(Bucket=bucket)
        return "ok"
    except Exception:
        logger.exception("storage_health_check_failed")
        return "error"
