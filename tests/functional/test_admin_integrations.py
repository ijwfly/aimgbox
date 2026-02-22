from aimg.db.repos.integrations import IntegrationRepo
from aimg.db.repos.partners import PartnerRepo


async def test_integration_create(admin_client, db_pool):
    # Create partner first
    partner = await PartnerRepo(db_pool).create("IntPartner")

    resp = await admin_client.post(
        "/admin/integrations",
        data={
            "partner_id": str(partner.id),
            "name": "Test Integration",
            "default_free_credits": "20",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Test Integration" in resp.text


async def test_integration_status_toggle(admin_client, db_pool):
    partner = await PartnerRepo(db_pool).create("StatusPartner")
    integration = await IntegrationRepo(db_pool).create(partner.id, "StatusInt")

    resp = await admin_client.post(
        f"/admin/integrations/{integration.id}/status",
        data={"status": "blocked"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    updated = await IntegrationRepo(db_pool).get_by_id(integration.id)
    assert updated.status == "blocked"


async def test_integration_update(admin_client, db_pool):
    partner = await PartnerRepo(db_pool).create("UpdPartner")
    integration = await IntegrationRepo(db_pool).create(partner.id, "UpdInt")

    resp = await admin_client.post(
        f"/admin/integrations/{integration.id}/update",
        data={"name": "Updated Name", "rate_limit_rpm": "200"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    updated = await IntegrationRepo(db_pool).get_by_id(integration.id)
    assert updated.name == "Updated Name"
    assert updated.rate_limit_rpm == 200
