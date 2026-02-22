from aimg.db.repos.credit_transactions import CreditTransactionRepo
from aimg.db.repos.integrations import IntegrationRepo
from aimg.db.repos.partners import PartnerRepo
from aimg.db.repos.users import UserRepo


async def test_user_search(admin_client, db_pool):
    partner = await PartnerRepo(db_pool).create("UserPartner")
    integration = await IntegrationRepo(db_pool).create(partner.id, "UserInt")
    await UserRepo(db_pool).get_or_create(
        integration.id, "external-user-123", default_free_credits=10,
    )

    resp = await admin_client.get("/admin/users?q=external-user")
    assert resp.status_code == 200
    assert "external-user-123" in resp.text


async def test_credit_adjustment(admin_client, db_pool):
    partner = await PartnerRepo(db_pool).create("CreditPartner")
    integration = await IntegrationRepo(db_pool).create(partner.id, "CreditInt")
    user = await UserRepo(db_pool).get_or_create(
        integration.id, "credit-user", default_free_credits=10,
    )

    resp = await admin_client.post(
        f"/admin/users/{user.id}/credits",
        data={"amount": "50", "credit_type": "free", "comment": "Test top-up"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    updated = await UserRepo(db_pool).get_by_id(user.id)
    assert updated.free_credits == 60

    # Check transaction was recorded
    txns = await CreditTransactionRepo(db_pool).list_by_user(user.id)
    assert len(txns) == 1
    assert txns[0].reason == "admin_adjustment"
    assert txns[0].comment == "Test top-up"


async def test_credit_adjustment_no_comment(admin_client, db_pool):
    partner = await PartnerRepo(db_pool).create("NoCommentPartner")
    integration = await IntegrationRepo(db_pool).create(partner.id, "NoCommentInt")
    user = await UserRepo(db_pool).get_or_create(
        integration.id, "nocomment-user", default_free_credits=10,
    )

    resp = await admin_client.post(
        f"/admin/users/{user.id}/credits",
        data={"amount": "5", "credit_type": "free", "comment": ""},
    )
    assert resp.status_code == 400
    assert "Comment is required" in resp.text
