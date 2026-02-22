from __future__ import annotations

import functools

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse


def require_auth(handler):
    @functools.wraps(handler)
    async def wrapper(request: Request, *args, **kwargs):
        if not request.state.admin_user:
            return RedirectResponse("/admin/login", status_code=302)
        return await handler(request, *args, **kwargs)
    return wrapper


def require_role(*roles: str):
    def decorator(handler):
        @functools.wraps(handler)
        async def wrapper(request: Request, *args, **kwargs):
            if not request.state.admin_user:
                return RedirectResponse("/admin/login", status_code=302)
            user_role = request.state.admin_user.get("role")
            if user_role not in roles:
                return HTMLResponse("Forbidden", status_code=403)
            return await handler(request, *args, **kwargs)
        return wrapper
    return decorator
