import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from aimg.common.health import check_database, check_redis, check_storage


@pytest.mark.asyncio
async def test_check_database_ok():
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=1)

    pool = MagicMock()

    @asynccontextmanager
    async def mock_acquire():
        yield conn

    pool.acquire = mock_acquire

    result = await check_database(pool)
    assert result == "ok"


@pytest.mark.asyncio
async def test_check_database_error():
    pool = MagicMock()

    @asynccontextmanager
    async def mock_acquire():
        raise Exception("Connection refused")
        yield  # noqa: unreachable

    pool.acquire = mock_acquire

    result = await check_database(pool)
    assert result == "error"


@pytest.mark.asyncio
async def test_check_redis_ok():
    client = AsyncMock()
    client.ping = AsyncMock(return_value=True)
    result = await check_redis(client)
    assert result == "ok"


@pytest.mark.asyncio
async def test_check_redis_error():
    client = AsyncMock()
    client.ping = AsyncMock(side_effect=Exception("Redis down"))
    result = await check_redis(client)
    assert result == "error"


@pytest.mark.asyncio
async def test_check_storage_ok():
    s3_client = AsyncMock()
    s3_client.head_bucket = AsyncMock(return_value={})
    result = await check_storage(s3_client, "test-bucket")
    assert result == "ok"
    s3_client.head_bucket.assert_called_once_with(Bucket="test-bucket")


@pytest.mark.asyncio
async def test_check_storage_error():
    s3_client = AsyncMock()
    s3_client.head_bucket = AsyncMock(side_effect=Exception("Bucket not found"))
    result = await check_storage(s3_client, "test-bucket")
    assert result == "error"
