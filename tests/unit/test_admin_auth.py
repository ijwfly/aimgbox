from aimg.admin.auth import (
    _sign_session,
    _verify_cookie,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password():
    hashed = hash_password("mypassword")
    assert verify_password("mypassword", hashed)


def test_verify_password_wrong():
    hashed = hash_password("mypassword")
    assert not verify_password("wrongpassword", hashed)


def test_sign_and_verify_session():
    secret = "test-secret"
    session_id = "abc-123"
    cookie = _sign_session(session_id, secret)
    assert session_id in cookie
    assert _verify_cookie(cookie, secret) == session_id


def test_verify_cookie_tampered():
    secret = "test-secret"
    cookie = _sign_session("abc-123", secret)
    tampered = cookie[:-2] + "xx"
    assert _verify_cookie(tampered, secret) is None


def test_verify_cookie_no_dot():
    assert _verify_cookie("no-dot-here", "secret") is None


def test_verify_cookie_wrong_secret():
    cookie = _sign_session("abc-123", "secret1")
    assert _verify_cookie(cookie, "secret2") is None
