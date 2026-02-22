from aimg.db.repos.audit_log import AuditLogRepo
from aimg.db.repos.partners import PartnerRepo


async def test_partner_list(admin_client):
    resp = await admin_client.get("/admin/partners")
    assert resp.status_code == 200
    assert "Partners" in resp.text


async def test_partner_create_and_detail(admin_client, db_pool):
    resp = await admin_client.post(
        "/admin/partners",
        data={"name": "Acme Corp"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Acme Corp" in resp.text

    # Check audit log
    audit_repo = AuditLogRepo(db_pool)
    entries = await audit_repo.list_entries(entity_type="partner")
    assert len(entries) >= 1
    assert entries[0].action == "partner.create"


async def test_partner_status_toggle(admin_client, db_pool):
    # Create partner
    repo = PartnerRepo(db_pool)
    partner = await repo.create("Toggle Partner")

    # Block
    resp = await admin_client.post(
        f"/admin/partners/{partner.id}/status",
        data={"status": "blocked"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "blocked" in resp.text

    # Verify in DB
    updated = await repo.get_by_id(partner.id)
    assert updated.status == "blocked"

    # Activate
    resp = await admin_client.post(
        f"/admin/partners/{partner.id}/status",
        data={"status": "active"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    updated = await repo.get_by_id(partner.id)
    assert updated.status == "active"
