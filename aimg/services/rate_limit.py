from __future__ import annotations

import time
from uuid import UUID

import redis.asyncio as aioredis


async def check_rate_limit(
    redis_client: aioredis.Redis,
    key: str,
    limit: int,
    window_seconds: int,
) -> tuple[bool, int, int, int]:
    """Sliding window rate limit via Redis sorted sets.

    Returns (allowed, limit, remaining, reset_timestamp).
    """
    now = time.time()
    window_start = now - window_seconds
    reset_ts = int(now) + window_seconds

    pipe = redis_client.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)
    pipe.zcard(key)
    results = await pipe.execute()
    current_count = results[1]

    if current_count >= limit:
        remaining = 0
        return False, limit, remaining, reset_ts

    # Add current request
    pipe2 = redis_client.pipeline()
    pipe2.zadd(key, {str(now): now})
    pipe2.expire(key, window_seconds)
    await pipe2.execute()

    remaining = max(0, limit - current_count - 1)
    return True, limit, remaining, reset_ts


async def check_integration_rpm(
    redis_client: aioredis.Redis, integration_id: UUID, rpm_limit: int
) -> tuple[bool, int, int, int]:
    key = f"aimg:ratelimit:integration:{integration_id}:rpm"
    return await check_rate_limit(redis_client, key, rpm_limit, 60)


async def check_user_jobs_per_hour(
    redis_client: aioredis.Redis, user_id: UUID, limit: int
) -> tuple[bool, int, int, int]:
    key = f"aimg:ratelimit:user:{user_id}:jph"
    return await check_rate_limit(redis_client, key, limit, 3600)
