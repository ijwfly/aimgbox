import pytest

from aimg.common.encryption import decrypt_value, encrypt_value


def test_roundtrip():
    key = "my-secret-key"
    plaintext = "hello world"
    ciphertext = encrypt_value(plaintext, key)
    assert decrypt_value(ciphertext, key) == plaintext


def test_different_keys_produce_different_ciphertext():
    plaintext = "same-data"
    ct1 = encrypt_value(plaintext, "key-one")
    ct2 = encrypt_value(plaintext, "key-two")
    assert ct1 != ct2


def test_wrong_key_raises():
    ciphertext = encrypt_value("secret", "correct-key")
    with pytest.raises(Exception):
        decrypt_value(ciphertext, "wrong-key")


def test_empty_string_roundtrip():
    key = "some-key"
    ciphertext = encrypt_value("", key)
    assert decrypt_value(ciphertext, key) == ""
