from fastapi import Request
from fastapi.responses import JSONResponse

from aimg.api.envelope import ApiResponse, ErrorDetail
from aimg.common.i18n import translate_error
from aimg.common.logging import request_id_var


class AppError(Exception):
    status_code: int = 500
    error_code: str = "INTERNAL"
    message: str = "Internal server error"

    def __init__(
        self,
        message: str | None = None,
        details: dict | None = None,
    ) -> None:
        self.message = message or self.__class__.message
        self.details = details
        super().__init__(self.message)


class AuthError(AppError):
    status_code = 401
    error_code = "UNAUTHORIZED"
    message = "Invalid or missing API key"


class ForbiddenError(AppError):
    status_code = 403
    error_code = "FORBIDDEN"
    message = "Access denied"


class NotFoundError(AppError):
    status_code = 404
    error_code = "NOT_FOUND"
    message = "Resource not found"


class InvalidInputError(AppError):
    status_code = 400
    error_code = "INVALID_INPUT"
    message = "Invalid input data"


class InvalidFileError(AppError):
    status_code = 400
    error_code = "INVALID_FILE"
    message = "Invalid file"


class InvalidJobTypeError(AppError):
    status_code = 400
    error_code = "INVALID_JOB_TYPE"
    message = "Unknown job type"


class InsufficientCreditsError(AppError):
    status_code = 402
    error_code = "INSUFFICIENT_CREDITS"
    message = "Insufficient credits"


class RateLimitedError(AppError):
    status_code = 429
    error_code = "RATE_LIMITED"
    message = "Rate limit exceeded"

    def __init__(
        self,
        message: str | None = None,
        retry_after: int = 60,
        details: dict | None = None,
    ) -> None:
        super().__init__(message, details)
        self.retry_after = retry_after


class InvalidAmountError(AppError):
    status_code = 400
    error_code = "INVALID_AMOUNT"
    message = "Invalid amount"


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    rid = request_id_var.get() or ""
    language = getattr(request.state, "language", "en")
    translated = translate_error(exc.error_code, language, **(exc.details or {}))
    body = ApiResponse(
        request_id=rid,
        success=False,
        error=ErrorDetail(
            code=exc.error_code,
            message=translated,
            details=exc.details,
        ),
    )
    headers = {}
    if isinstance(exc, RateLimitedError):
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(
        status_code=exc.status_code,
        content=body.model_dump(mode="json"),
        headers=headers,
    )
