import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from aimg.common.logging import request_id_var


def _resolve_language(request: Request) -> str:
    lang = request.query_params.get("lang")
    if lang:
        return lang
    accept = request.headers.get("Accept-Language", "")
    if accept:
        # Take the first language tag (e.g. "ru-RU,ru;q=0.9" → "ru")
        primary = accept.split(",")[0].split(";")[0].strip()
        code = primary.split("-")[0]
        if code:
            return code
    return "en"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request_id_var.set(rid)
        request.state.request_id = rid
        request.state.language = _resolve_language(request)

        response = await call_next(request)

        response.headers["X-Request-ID"] = rid

        if hasattr(request.state, "rate_limit_limit"):
            response.headers["X-RateLimit-Limit"] = str(request.state.rate_limit_limit)
            response.headers["X-RateLimit-Remaining"] = str(request.state.rate_limit_remaining)
            response.headers["X-RateLimit-Reset"] = str(request.state.rate_limit_reset)

        return response
