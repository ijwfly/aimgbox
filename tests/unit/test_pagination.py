from datetime import UTC, datetime
from uuid import uuid4

from aimg.common.pagination import clamp_limit, decode_cursor, encode_cursor


def test_roundtrip():
    now = datetime(2024, 6, 15, 12, 30, 0, tzinfo=UTC)
    uid = uuid4()
    cursor = encode_cursor(now, uid)
    decoded_dt, decoded_id = decode_cursor(cursor)
    assert decoded_dt == now
    assert decoded_id == uid


def test_clamp_limit_none():
    assert clamp_limit(None) == 20


def test_clamp_limit_zero():
    assert clamp_limit(0) == 1


def test_clamp_limit_over_max():
    assert clamp_limit(200) == 100


def test_clamp_limit_normal():
    assert clamp_limit(50) == 50


def test_clamp_limit_custom_defaults():
    assert clamp_limit(None, default=10, maximum=50) == 10
    assert clamp_limit(60, default=10, maximum=50) == 50
