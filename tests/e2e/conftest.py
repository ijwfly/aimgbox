import asyncio
import os

import asyncpg
import httpx
import pytest


@pytest.fixture
def base_url():
    return os.environ.get("AIMG_API_URL", "http://localhost:8010")


@pytest.fixture
def admin_url():
    return os.environ.get("AIMG_ADMIN_URL", "http://localhost:8001")


@pytest.fixture
def api_key():
    """Must be set via env var after running `aimg seed`."""
    key = os.environ.get("AIMG_API_KEY")
    if not key:
        pytest.skip("AIMG_API_KEY not set; run `aimg seed` first")
    return key


@pytest.fixture
def client(base_url):
    with httpx.Client(base_url=base_url) as client:
        yield client


@pytest.fixture
def admin_client(admin_url):
    """Logged-in admin httpx.Client with session cookie."""
    with httpx.Client(base_url=admin_url, follow_redirects=True) as c:
        resp = c.post(
            "/admin/login",
            data={"username": "admin", "password": "admin"},
        )
        assert resp.status_code == 200, f"Admin login failed: {resp.status_code}"
        yield c


@pytest.fixture
def db_query():
    """Run a direct SQL query against the test database."""
    db_host = os.environ.get("AIMG_DB_HOST", "localhost")
    db_port = int(os.environ.get("AIMG_DB_PORT", "5433"))
    db_name = os.environ.get("AIMG_DB_NAME", "aimg")
    db_user = os.environ.get("AIMG_DB_USER", "aimg")
    db_password = os.environ.get("AIMG_DB_PASSWORD", "aimg")

    dsn = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    async def _query(sql: str, *args):
        conn = await asyncpg.connect(dsn)
        try:
            return await conn.fetch(sql, *args)
        finally:
            await conn.close()

    def sync_query(sql: str, *args):
        return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            _query(sql, *args)
        )

    return sync_query
