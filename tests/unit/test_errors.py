import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aimg.api.errors import (
    AppError,
    AuthError,
    ForbiddenError,
    InsufficientCreditsError,
    InvalidAmountError,
    InvalidFileError,
    InvalidInputError,
    InvalidJobTypeError,
    NotFoundError,
    RateLimitedError,
    app_error_handler,
)


def test_app_error_defaults():
    err = AppError()
    assert err.status_code == 500
    assert err.error_code == "INTERNAL"
    assert err.message == "Internal server error"
    assert err.details is None


def test_app_error_custom_message():
    err = AppError(message="Custom error", details={"key": "val"})
    assert err.message == "Custom error"
    assert err.details == {"key": "val"}


def test_auth_error():
    err = AuthError()
    assert err.status_code == 401
    assert err.error_code == "UNAUTHORIZED"


def test_forbidden_error():
    err = ForbiddenError()
    assert err.status_code == 403
    assert err.error_code == "FORBIDDEN"


def test_not_found_error():
    err = NotFoundError()
    assert err.status_code == 404
    assert err.error_code == "NOT_FOUND"


def test_invalid_input_error():
    err = InvalidInputError()
    assert err.status_code == 400
    assert err.error_code == "INVALID_INPUT"


def test_invalid_file_error():
    err = InvalidFileError()
    assert err.status_code == 400
    assert err.error_code == "INVALID_FILE"


def test_invalid_job_type_error():
    err = InvalidJobTypeError()
    assert err.status_code == 400
    assert err.error_code == "INVALID_JOB_TYPE"


def test_insufficient_credits_error():
    err = InsufficientCreditsError()
    assert err.status_code == 402
    assert err.error_code == "INSUFFICIENT_CREDITS"


def test_rate_limited_error_default_retry():
    err = RateLimitedError()
    assert err.status_code == 429
    assert err.error_code == "RATE_LIMITED"
    assert err.retry_after == 60


def test_rate_limited_error_custom_retry():
    err = RateLimitedError(retry_after=120)
    assert err.retry_after == 120


def test_invalid_amount_error():
    err = InvalidAmountError()
    assert err.status_code == 400
    assert err.error_code == "INVALID_AMOUNT"


@pytest.mark.asyncio
async def test_error_handler_returns_json():
    request = MagicMock()
    request.state.language = "en"

    exc = NotFoundError(message="Job not found", details={"job_id": "123"})

    with patch("aimg.api.errors.request_id_var") as rid_var, \
         patch("aimg.api.errors.translate_error", return_value="Resource not found"):
        rid_var.get.return_value = "test-rid"
        resp = await app_error_handler(request, exc)

    assert resp.status_code == 404
    import json
    body = json.loads(resp.body)
    assert body["request_id"] == "test-rid"
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_error_handler_rate_limited_includes_retry_after():
    request = MagicMock()
    request.state.language = "en"

    exc = RateLimitedError(retry_after=30)

    with patch("aimg.api.errors.request_id_var") as rid_var, \
         patch("aimg.api.errors.translate_error", return_value="Rate limit exceeded"):
        rid_var.get.return_value = "test-rid"
        resp = await app_error_handler(request, exc)

    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "30"
