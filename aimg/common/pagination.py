import base64
from datetime import datetime
from uuid import UUID


def encode_cursor(created_at: datetime, record_id: UUID) -> str:
    raw = f"{created_at.isoformat()}:{record_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    iso_str, uuid_str = raw.rsplit(":", 1)
    return datetime.fromisoformat(iso_str), UUID(uuid_str)


def clamp_limit(limit: int | None, default: int = 20, maximum: int = 100) -> int:
    if limit is None:
        return default
    return max(1, min(limit, maximum))
