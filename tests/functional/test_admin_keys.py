from aimg.db.repos.api_keys import ApiKeyRepo
from aimg.db.repos.integrations import IntegrationRepo
from aimg.db.repos.partners import PartnerRepo


async def test_generate_and_revoke_key(admin_client, db_pool, redis_client):
    partner = await PartnerRepo(db_pool).create("KeyPartner")
    integration = await IntegrationRepo(db_pool).create(partner.id, "KeyInt")

    # Generate
    resp = await admin_client.post(
        f"/admin/integrations/{integration.id}/keys",
        data={"label": "test-key"},
    )
    assert resp.status_code == 200
    assert "Copy this JWT token" in resp.text

    # Verify key in DB
    keys = await ApiKeyRepo(db_pool).list_by_integration(integration.id)
    assert len(keys) == 1
    assert keys[0].label == "test-key"
    assert not keys[0].is_revoked

    # Revoke
    key_id = keys[0].id
    resp = await admin_client.post(
        f"/admin/keys/{key_id}/revoke",
        follow_redirects=True,
    )
    assert resp.status_code == 200

    revoked = await ApiKeyRepo(db_pool).get_by_id(key_id)
    assert revoked.is_revoked

    # Check Redis revoked set
    is_member = await redis_client.sismember("aimg:revoked_keys", revoked.key_hash)
    assert is_member
