import pytest


@pytest.mark.asyncio
async def test_topup_happy_path(client, seeded_data):
    headers = {
        "X-API-Key": seeded_data["token"],
    }

    resp = await client.post(
        "/v1/billing/topup",
        headers=headers,
        json={
            "external_user_id": "billing-user-1",
            "amount": 100,
            "external_transaction_id": "txn-001",
        },
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["paid_credits"] == 100
    assert data["external_user_id"] == "billing-user-1"
    assert "transaction_id" in data
    assert "user_id" in data


@pytest.mark.asyncio
async def test_topup_idempotency_by_external_txn_id(client, seeded_data):
    headers = {
        "X-API-Key": seeded_data["token"],
    }

    body = {
        "external_user_id": "billing-user-2",
        "amount": 50,
        "external_transaction_id": "txn-dup-001",
    }

    r1 = await client.post("/v1/billing/topup", headers=headers, json=body)
    assert r1.status_code == 201

    r2 = await client.post("/v1/billing/topup", headers=headers, json=body)
    # Should return the same result (idempotent)
    assert r2.status_code in (200, 201)
    assert r2.json()["data"]["paid_credits"] == r1.json()["data"]["paid_credits"]


@pytest.mark.asyncio
async def test_topup_invalid_amount(client, seeded_data):
    headers = {
        "X-API-Key": seeded_data["token"],
    }

    resp = await client.post(
        "/v1/billing/topup",
        headers=headers,
        json={
            "external_user_id": "billing-user-3",
            "amount": 0,
            "external_transaction_id": "txn-bad",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_AMOUNT"


@pytest.mark.asyncio
async def test_topup_negative_amount(client, seeded_data):
    headers = {
        "X-API-Key": seeded_data["token"],
    }

    resp = await client.post(
        "/v1/billing/topup",
        headers=headers,
        json={
            "external_user_id": "billing-user-4",
            "amount": -10,
            "external_transaction_id": "txn-neg",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_check_can_afford(client, seeded_data):
    headers = {
        "X-API-Key": seeded_data["token"],
        "X-External-User-Id": "check-user-1",
    }

    resp = await client.post(
        "/v1/billing/check",
        headers=headers,
        json={"job_type": "remove_bg"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["can_afford"] is True
    assert data["credit_cost"] == 1
    assert data["free_credits"] == 10
    assert data["total_credits"] == 10


@pytest.mark.asyncio
async def test_check_cannot_afford(client, seeded_data, db_pool):
    headers = {
        "X-API-Key": seeded_data["token"],
        "X-External-User-Id": "check-user-broke",
    }

    # First create the user by accessing balance
    resp = await client.get("/v1/users/me/balance", headers=headers)
    assert resp.status_code == 200

    # Set credits to 0
    from aimg.db.repos.users import UserRepo

    user_repo = UserRepo(db_pool)
    user = await user_repo.get_or_create(
        seeded_data["integration"].id, "check-user-broke"
    )
    await user_repo.force_set_credits(user.id, 0, 0)

    resp = await client.post(
        "/v1/billing/check",
        headers=headers,
        json={"job_type": "remove_bg"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["can_afford"] is False
