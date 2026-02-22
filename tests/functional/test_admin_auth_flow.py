import httpx

from aimg.admin.app import create_admin_app
from aimg.admin.auth import hash_password
from aimg.common.connections import create_db_pool, create_redis_client
from aimg.db.repos.admin_users import AdminUserRepo


async def test_login_page(settings):
    app = create_admin_app(settings)
    app.state.settings = settings
    app.state.db_pool = await create_db_pool(settings)
    app.state.redis = create_redis_client(settings)

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resp = await client.get("/admin/login")
            assert resp.status_code == 200
            assert "Admin Login" in resp.text
    finally:
        await app.state.db_pool.close()
        await app.state.redis.aclose()


async def test_login_and_redirect(settings, db_pool):
    # Create admin user
    repo = AdminUserRepo(db_pool)
    await repo.create("logintest", hash_password("secret"), "super_admin")

    app = create_admin_app(settings)
    app.state.settings = settings
    app.state.db_pool = await create_db_pool(settings)
    app.state.redis = create_redis_client(settings)

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            resp = await client.post("/admin/login", data={
                "username": "logintest",
                "password": "secret",
            })
            assert resp.status_code == 302
            assert resp.headers["location"] == "/admin/dashboard"
            assert "aimg_admin_session" in resp.cookies
    finally:
        await app.state.db_pool.close()
        await app.state.redis.aclose()


async def test_login_wrong_password(settings, db_pool):
    repo = AdminUserRepo(db_pool)
    await repo.create("wrongpass", hash_password("correct"), "admin")

    app = create_admin_app(settings)
    app.state.settings = settings
    app.state.db_pool = await create_db_pool(settings)
    app.state.redis = create_redis_client(settings)

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resp = await client.post("/admin/login", data={
                "username": "wrongpass",
                "password": "wrong",
            })
            assert resp.status_code == 401
            assert "Invalid" in resp.text
    finally:
        await app.state.db_pool.close()
        await app.state.redis.aclose()


async def test_unauthenticated_redirect(settings):
    app = create_admin_app(settings)
    app.state.settings = settings
    app.state.db_pool = await create_db_pool(settings)
    app.state.redis = create_redis_client(settings)

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            resp = await client.get("/admin/dashboard")
            assert resp.status_code == 302
            assert "/admin/login" in resp.headers["location"]
    finally:
        await app.state.db_pool.close()
        await app.state.redis.aclose()


async def test_logout(settings, db_pool):
    repo = AdminUserRepo(db_pool)
    await repo.create("logouttest", hash_password("pass"), "admin")

    app = create_admin_app(settings)
    app.state.settings = settings
    app.state.db_pool = await create_db_pool(settings)
    app.state.redis = create_redis_client(settings)

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            # Login first
            login_resp = await client.post("/admin/login", data={
                "username": "logouttest",
                "password": "pass",
            })
            assert login_resp.status_code == 302
            client.cookies.update(login_resp.cookies)

            # Logout
            logout_resp = await client.get("/admin/logout")
            assert logout_resp.status_code == 302
            assert "/admin/login" in logout_resp.headers["location"]
    finally:
        await app.state.db_pool.close()
        await app.state.redis.aclose()
