import fakeredis.aioredis
import pytest

from aimg.services.rate_limit import check_rate_limit


@pytest.fixture
def redis_client():
    return fakeredis.aioredis.FakeRedis()


@pytest.mark.asyncio
async def test_allowed_under_limit(redis_client):
    allowed, limit, remaining, reset_ts = await check_rate_limit(
        redis_client, "test:key", 5, 60
    )
    assert allowed is True
    assert limit == 5
    assert remaining == 4


@pytest.mark.asyncio
async def test_denied_at_limit(redis_client):
    key = "test:deny"
    for _ in range(5):
        await check_rate_limit(redis_client, key, 5, 60)

    allowed, limit, remaining, reset_ts = await check_rate_limit(
        redis_client, key, 5, 60
    )
    assert allowed is False
    assert remaining == 0


@pytest.mark.asyncio
async def test_remaining_decreases(redis_client):
    key = "test:remaining"
    _, _, r1, _ = await check_rate_limit(redis_client, key, 5, 60)
    _, _, r2, _ = await check_rate_limit(redis_client, key, 5, 60)
    _, _, r3, _ = await check_rate_limit(redis_client, key, 5, 60)
    assert r1 == 4
    assert r2 == 3
    assert r3 == 2


@pytest.mark.asyncio
async def test_denied_does_not_increase_count(redis_client):
    key = "test:no_inc"
    # Fill to limit
    for _ in range(3):
        await check_rate_limit(redis_client, key, 3, 60)

    # Denied request should not add to sorted set
    allowed, _, _, _ = await check_rate_limit(redis_client, key, 3, 60)
    assert allowed is False

    count = await redis_client.zcard(key)
    assert count == 3  # Not 4
