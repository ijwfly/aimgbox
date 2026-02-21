import asyncpg
import redis.asyncio as aioredis
from fastapi import Request

from aimg.common.settings import Settings


def get_db_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.db_pool


def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


def get_s3_client(request: Request) -> object:
    return request.app.state.s3_client


def get_settings(request: Request) -> Settings:
    return request.app.state.settings
