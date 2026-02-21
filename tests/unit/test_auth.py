from uuid import uuid4

import pytest

from aimg.services.auth import generate_api_key, hash_api_key, verify_api_key

SECRET = "test-secret-key"


def test_generate_and_verify():
    integration_id = uuid4()
    partner_id = uuid4()
    key_id = uuid4()

    token = generate_api_key(integration_id, partner_id, key_id, SECRET)
    assert isinstance(token, str)

    payload = verify_api_key(token, SECRET)
    assert payload["integration_id"] == str(integration_id)
    assert payload["partner_id"] == str(partner_id)
    assert payload["key_id"] == str(key_id)
    assert "iat" in payload


def test_verify_wrong_secret():
    token = generate_api_key(uuid4(), uuid4(), uuid4(), SECRET)
    with pytest.raises(Exception):
        verify_api_key(token, "wrong-secret")


def test_verify_invalid_token():
    with pytest.raises(Exception):
        verify_api_key("not-a-jwt", SECRET)


def test_hash_api_key():
    token = "some-token"
    h = hash_api_key(token)
    assert isinstance(h, str)
    assert len(h) == 64  # SHA-256 hex digest
    assert h == hash_api_key(token)  # deterministic


def test_hash_different_tokens():
    h1 = hash_api_key("token-1")
    h2 = hash_api_key("token-2")
    assert h1 != h2
