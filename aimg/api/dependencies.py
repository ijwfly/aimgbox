from typing import Annotated

import asyncpg
import redis.asyncio as aioredis
import structlog
from fastapi import Depends, Header, Request

from aimg.api.errors import AuthError
from aimg.common.settings import Settings
from aimg.db.models import Integration, User
from aimg.db.repos.api_keys import ApiKeyRepo
from aimg.db.repos.integrations import IntegrationRepo
from aimg.db.repos.users import UserRepo
from aimg.services.auth import hash_api_key, verify_api_key

logger = structlog.get_logger()


def get_db_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.db_pool


def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


def get_s3_client(request: Request) -> object:
    return request.app.state.s3_client


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_current_integration(
    x_api_key: Annotated[str, Header()],
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    redis_client: aioredis.Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> Integration:
    try:
        payload = verify_api_key(x_api_key, settings.jwt_secret)
    except Exception:
        raise AuthError("Invalid API key")

    key_id = payload.get("key_id")
    if not key_id:
        raise AuthError("Invalid API key payload")

    # Check revocation cache
    is_revoked = await redis_client.sismember("aimg:revoked_keys", key_id)
    if is_revoked:
        raise AuthError("API key has been revoked")

    # Check key in DB
    key_hash = hash_api_key(x_api_key)
    api_key_repo = ApiKeyRepo(db_pool)
    api_key = await api_key_repo.get_by_hash(key_hash)
    if not api_key:
        raise AuthError("API key not found")
    if api_key.is_revoked:
        await redis_client.sadd("aimg:revoked_keys", str(api_key.id))
        raise AuthError("API key has been revoked")

    # Load integration
    integration_repo = IntegrationRepo(db_pool)
    integration = await integration_repo.get_by_id(api_key.integration_id)
    if not integration:
        raise AuthError("Integration not found")
    if integration.status != "active":
        raise AuthError("Integration is not active")

    return integration


async def get_current_user(
    x_external_user_id: Annotated[str, Header()],
    integration: Integration = Depends(get_current_integration),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> User:
    user_repo = UserRepo(db_pool)
    user = await user_repo.get_or_create(
        integration.id,
        x_external_user_id,
        default_free_credits=integration.default_free_credits,
    )
    return user
