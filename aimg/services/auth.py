import hashlib
import time
from uuid import UUID

import jwt


def generate_api_key(
    integration_id: UUID, partner_id: UUID, key_id: UUID, secret: str
) -> str:
    payload = {
        "integration_id": str(integration_id),
        "partner_id": str(partner_id),
        "key_id": str(key_id),
        "iat": int(time.time()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_api_key(token: str, secret: str) -> dict:
    return jwt.decode(token, secret, algorithms=["HS256"])


def hash_api_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
