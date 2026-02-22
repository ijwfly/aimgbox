from aimg.admin.auth import hash_password
from aimg.db.repos.admin_users import AdminUserRepo
from aimg.db.repos.audit_log import AuditLogRepo


async def test_admin_user_crud(db_pool):
    repo = AdminUserRepo(db_pool)

    user = await repo.create("testuser", hash_password("pass"), "admin")
    assert user.username == "testuser"
    assert user.role == "admin"
    assert user.status == "active"

    found = await repo.get_by_username("testuser")
    assert found.id == user.id

    found_by_id = await repo.get_by_id(user.id)
    assert found_by_id.username == "testuser"

    updated = await repo.update_status(user.id, "blocked")
    assert updated.status == "blocked"

    updated = await repo.update_password(user.id, hash_password("newpass"))
    assert updated is not None

    all_users = await repo.list_all()
    assert len(all_users) == 1

    count = await repo.count()
    assert count == 1


async def test_admin_user_not_found(db_pool):
    repo = AdminUserRepo(db_pool)
    assert await repo.get_by_username("nonexistent") is None


async def test_audit_log_crud(db_pool):
    # Create admin user first for FK
    admin_repo = AdminUserRepo(db_pool)
    admin = await admin_repo.create("audituser", hash_password("p"), "super_admin")

    repo = AuditLogRepo(db_pool)
    entry = await repo.create(
        admin_user_id=admin.id,
        action="partner.create",
        entity_type="partner",
        entity_id=admin.id,
        details={"name": "Test"},
        ip_address="127.0.0.1",
    )
    assert entry.action == "partner.create"
    assert entry.entity_type == "partner"

    entries = await repo.list_entries()
    assert len(entries) == 1

    count = await repo.count()
    assert count == 1


async def test_audit_log_filtering(db_pool):
    admin_repo = AdminUserRepo(db_pool)
    admin = await admin_repo.create("filteruser", hash_password("p"), "super_admin")

    repo = AuditLogRepo(db_pool)
    await repo.create(admin.id, "partner.create", "partner")
    await repo.create(admin.id, "partner.update", "partner")
    await repo.create(admin.id, "integration.create", "integration")

    partner_entries = await repo.list_entries(entity_type="partner")
    assert len(partner_entries) == 2

    create_entries = await repo.list_entries(action_prefix="partner.create")
    assert len(create_entries) == 1

    count = await repo.count(entity_type="partner")
    assert count == 2
