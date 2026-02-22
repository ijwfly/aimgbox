from __future__ import annotations

from starlette.requests import Request
from starlette.responses import RedirectResponse

from aimg.admin.auth import (
    create_session,
    destroy_session,
    verify_password,
)
from aimg.admin.middleware import COOKIE_NAME
from aimg.db.repos.admin_users import AdminUserRepo


async def login_page(request: Request):
    templates = request.app.state.templates
    if request.state.admin_user:
        return RedirectResponse("/admin/dashboard", status_code=302)
    return templates.TemplateResponse(request, "login.html")


async def login_submit(request: Request):
    templates = request.app.state.templates
    form = await request.form()
    username = form.get("username", "").strip()
    password = form.get("password", "")

    repo = AdminUserRepo(request.app.state.db_pool)
    user = await repo.get_by_username(username)

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Invalid username or password"}, status_code=401
        )

    if user.status != "active":
        return templates.TemplateResponse(
            request, "login.html", {"error": "Account is disabled"}, status_code=403
        )

    secret = request.app.state.settings.admin_session_secret
    cookie_value = await create_session(request.app.state.redis, user, secret)

    response = RedirectResponse("/admin/dashboard", status_code=302)
    response.set_cookie(
        COOKIE_NAME,
        cookie_value,
        httponly=True,
        samesite="strict",
        max_age=86400,
    )
    return response


async def logout(request: Request):
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie:
        secret = request.app.state.settings.admin_session_secret
        await destroy_session(request.app.state.redis, cookie, secret)

    response = RedirectResponse("/admin/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response
