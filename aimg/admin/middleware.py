from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from aimg.admin.auth import load_session

COOKIE_NAME = "aimg_admin_session"
PUBLIC_PATHS = {"/admin/login", "/admin/health", "/health"}


class AdminSessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request.state.admin_user = None

        path = request.url.path.rstrip("/") or "/"
        if path in PUBLIC_PATHS:
            return await call_next(request)

        cookie = request.cookies.get(COOKIE_NAME)
        if cookie:
            redis_client = request.app.state.redis
            secret = request.app.state.settings.admin_session_secret
            session_data = await load_session(redis_client, cookie, secret)
            if session_data:
                request.state.admin_user = session_data

        return await call_next(request)
