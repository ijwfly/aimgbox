from __future__ import annotations

import hashlib
import hmac
import json
from uuid import uuid4

import bcrypt
import redis.asyncio as aioredis

from aimg.db.models import AdminUser

SESSION_TTL = 86400  # 24 hours
SESSION_PREFIX = "aimg:admin_session:"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    result = bcrypt.checkpw(plain.encode(), hashed.encode())
    # Use hmac.compare_digest on the boolean-derived bytes for timing safety
    return hmac.compare_digest(
        b"y" if result else b"n",
        b"y",
    )


def _sign_session(session_id: str, secret: str) -> str:
    sig = hmac.new(secret.encode(), session_id.encode(), hashlib.sha256).hexdigest()
    return f"{session_id}.{sig}"


def _verify_cookie(cookie_value: str, secret: str) -> str | None:
    parts = cookie_value.split(".", 1)
    if len(parts) != 2:
        return None
    session_id, sig = parts
    expected = hmac.new(secret.encode(), session_id.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    return session_id


async def create_session(
    redis_client: aioredis.Redis, admin_user: AdminUser, secret: str
) -> str:
    session_id = str(uuid4())
    data = json.dumps({
        "id": str(admin_user.id),
        "username": admin_user.username,
        "role": admin_user.role,
    })
    await redis_client.set(f"{SESSION_PREFIX}{session_id}", data, ex=SESSION_TTL)
    return _sign_session(session_id, secret)


async def load_session(
    redis_client: aioredis.Redis, cookie_value: str, secret: str
) -> dict | None:
    session_id = _verify_cookie(cookie_value, secret)
    if not session_id:
        return None
    data = await redis_client.get(f"{SESSION_PREFIX}{session_id}")
    if not data:
        return None
    return json.loads(data)


async def destroy_session(
    redis_client: aioredis.Redis, cookie_value: str, secret: str
) -> None:
    session_id = _verify_cookie(cookie_value, secret)
    if session_id:
        await redis_client.delete(f"{SESSION_PREFIX}{session_id}")
