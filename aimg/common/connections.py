import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as aioredis
from aiobotocore.session import AioSession

from aimg.common.settings import Settings


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    await conn.set_type_codec(
        "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def create_db_pool(settings: Settings) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn=settings.database_url, init=_init_connection)


def create_redis_client(settings: Settings) -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


@asynccontextmanager
async def create_s3_client(settings: Settings) -> AsyncGenerator:
    session = AioSession()
    async with session.create_client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="us-east-1",
    ) as client:
        yield client
