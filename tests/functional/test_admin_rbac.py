"""Tests for admin role-based access control.

Spec reference: 07-admin-and-operations.md, Section 20
- super_admin: full access
- admin: partners/integrations/users/keys management
- viewer: read-only access
"""
import httpx

from aimg.admin.app import create_admin_app
from aimg.admin.auth import create_session, hash_password
from aimg.common.connections import create_db_pool, create_redis_client
from aimg.db.repos.admin_users import AdminUserRepo
from aimg.db.repos.partners import PartnerRepo
from aimg.db.repos.providers import ProviderRepo


async def _make_admin_client(settings, db_pool, role):
    """Create an admin client with a specific role."""
    repo = AdminUserRepo(db_pool)
    username = f"test_{role}_{id(role)}"
    pw_hash = hash_password("testpass")
    user = await repo.create(username, pw_hash, role)

    app = create_admin_app(settings)
    app.state.settings = settings
    app.state.db_pool = await create_db_pool(settings)
    app.state.redis = create_redis_client(settings)

    cookie_value = await create_session(
        app.state.redis, user, settings.admin_session_secret,
    )

    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        cookies={"aimg_admin_session": cookie_value},
    )
    return client, app


async def test_viewer_cannot_create_partner(settings, db_pool):
    """Viewer role should get 403 when trying to create a partner."""
    client, app = await _make_admin_client(settings, db_pool, "viewer")
    try:
        resp = await client.post("/admin/partners", data={"name": "Forbidden Partner"})
        assert resp.status_code == 403
    finally:
        await client.aclose()
        await app.state.db_pool.close()
        await app.state.redis.aclose()


async def test_viewer_can_list_partners(settings, db_pool):
    """Viewer should be able to read partner list."""
    client, app = await _make_admin_client(settings, db_pool, "viewer")
    try:
        resp = await client.get("/admin/partners")
        assert resp.status_code == 200
    finally:
        await client.aclose()
        await app.state.db_pool.close()
        await app.state.redis.aclose()


async def test_admin_can_create_partner(settings, db_pool):
    """Admin role should be able to create a partner."""
    client, app = await _make_admin_client(settings, db_pool, "admin")
    try:
        resp = await client.post(
            "/admin/partners",
            data={"name": "Admin Partner"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
    finally:
        await client.aclose()
        await app.state.db_pool.close()
        await app.state.redis.aclose()


async def test_viewer_cannot_update_job_type(settings, db_pool):
    """Viewer should get 403 on job type update (super_admin only)."""
    from aimg.db.repos.job_types import JobTypeRepo
    jt_repo = JobTypeRepo(db_pool)
    jt = await jt_repo.upsert("rbac_test", "RBAC Test", "Test", {}, {})

    client, app = await _make_admin_client(settings, db_pool, "viewer")
    try:
        resp = await client.post(
            f"/admin/job-types/{jt.id}",
            data={"credit_cost": "5"},
        )
        assert resp.status_code == 403
    finally:
        await client.aclose()
        await app.state.db_pool.close()
        await app.state.redis.aclose()


async def test_admin_cannot_update_job_type(settings, db_pool):
    """Admin role should get 403 on job type update (requires super_admin)."""
    from aimg.db.repos.job_types import JobTypeRepo
    jt_repo = JobTypeRepo(db_pool)
    jt = await jt_repo.upsert("rbac_test2", "RBAC Test2", "Test", {}, {})

    client, app = await _make_admin_client(settings, db_pool, "admin")
    try:
        resp = await client.post(
            f"/admin/job-types/{jt.id}",
            data={"credit_cost": "5"},
        )
        assert resp.status_code == 403
    finally:
        await client.aclose()
        await app.state.db_pool.close()
        await app.state.redis.aclose()


async def test_super_admin_can_create_provider(settings, db_pool):
    """Super admin should be able to create a provider."""
    client, app = await _make_admin_client(settings, db_pool, "super_admin")
    try:
        resp = await client.post(
            "/admin/providers",
            data={
                "slug": "rbac-test-provider",
                "name": "Test Provider",
                "adapter_class": "some.TestClass",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
    finally:
        await client.aclose()
        await app.state.db_pool.close()
        await app.state.redis.aclose()


async def test_viewer_cannot_create_provider(settings, db_pool):
    """Viewer should get 403 when trying to create a provider."""
    client, app = await _make_admin_client(settings, db_pool, "viewer")
    try:
        resp = await client.post(
            "/admin/providers",
            data={
                "slug": "viewer-provider",
                "name": "Forbidden",
                "adapter_class": "some.Class",
            },
        )
        assert resp.status_code == 403
    finally:
        await client.aclose()
        await app.state.db_pool.close()
        await app.state.redis.aclose()
