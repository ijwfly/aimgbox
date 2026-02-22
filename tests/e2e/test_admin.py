import uuid


def test_admin_create_partner_and_integration(admin_client, db_query):
    """AC 18: Admin can create a partner and an integration."""
    partner_name = f"E2E Partner {uuid.uuid4().hex[:8]}"

    # Create partner via admin form
    resp = admin_client.post(
        "/admin/partners",
        data={"name": partner_name},
    )
    assert resp.status_code == 200  # follows redirect to detail page

    # Find the partner in DB
    rows = db_query("SELECT * FROM partners WHERE name = $1", partner_name)
    assert len(rows) == 1
    partner_id = rows[0]["id"]

    # Create integration for this partner
    integration_name = f"E2E Integration {uuid.uuid4().hex[:8]}"
    resp = admin_client.post(
        "/admin/integrations",
        data={
            "name": integration_name,
            "partner_id": str(partner_id),
            "default_free_credits": "5",
        },
    )
    assert resp.status_code == 200  # follows redirect

    rows = db_query(
        "SELECT * FROM integrations WHERE name = $1", integration_name,
    )
    assert len(rows) == 1
    assert rows[0]["partner_id"] == partner_id
    assert rows[0]["default_free_credits"] == 5


def test_admin_generate_and_revoke_key(admin_client, db_query):
    """AC 19: Admin can generate and revoke API keys."""
    # Use existing seed integration — find it
    rows = db_query(
        "SELECT id FROM integrations WHERE name = 'Test Integration' LIMIT 1"
    )
    if not rows:
        # Create one if not found
        partner_rows = db_query("SELECT id FROM partners LIMIT 1")
        assert partner_rows
        admin_client.post(
            "/admin/integrations",
            data={
                "name": "Test Integration",
                "partner_id": str(partner_rows[0]["id"]),
                "default_free_credits": "10",
            },
        )
        rows = db_query(
            "SELECT id FROM integrations WHERE name = 'Test Integration' LIMIT 1"
        )

    integration_id = rows[0]["id"]

    # Generate key
    resp = admin_client.post(
        f"/admin/integrations/{integration_id}/keys",
        data={"label": "e2e-test-key"},
    )
    assert resp.status_code == 200

    # Find generated key
    key_rows = db_query(
        "SELECT * FROM api_keys WHERE integration_id = $1 AND label = $2",
        integration_id, "e2e-test-key",
    )
    assert len(key_rows) >= 1
    key_id = key_rows[-1]["id"]
    assert key_rows[-1]["is_revoked"] is False

    # Revoke key
    resp = admin_client.post(f"/admin/keys/{key_id}/revoke")
    assert resp.status_code == 200  # follows redirect

    # Verify revoked
    key_rows = db_query("SELECT * FROM api_keys WHERE id = $1", key_id)
    assert key_rows[0]["is_revoked"] is True


def test_admin_view_jobs(admin_client):
    """AC 20: Admin can view jobs list and filter by status."""
    resp = admin_client.get("/admin/jobs")
    assert resp.status_code == 200

    resp = admin_client.get("/admin/jobs?status=succeeded")
    assert resp.status_code == 200


def test_admin_credit_adjustment(admin_client, db_query):
    """AC 21: Admin can adjust credits (requires comment)."""
    # Find a user
    rows = db_query("SELECT id FROM users LIMIT 1")
    if not rows:
        return  # skip if no users exist
    user_id = rows[0]["id"]

    # Attempt without comment -> should fail (400)
    resp = admin_client.post(
        f"/admin/users/{user_id}/credits",
        data={"amount": "5", "credit_type": "free", "comment": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 400

    # With comment -> should succeed (302 redirect)
    resp = admin_client.post(
        f"/admin/users/{user_id}/credits",
        data={"amount": "5", "credit_type": "free", "comment": "E2E test adjustment"},
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_admin_export_csv(admin_client):
    """AC 22: Admin can export jobs as CSV."""
    resp = admin_client.get("/admin/jobs/export", follow_redirects=False)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    assert "attachment" in resp.headers.get("content-disposition", "")
    body = resp.text
    assert "id" in body.split("\n")[0]
    assert "status" in body.split("\n")[0]


def test_admin_audit_log(admin_client):
    """AC 23: Admin can view audit log."""
    resp = admin_client.get("/admin/audit")
    assert resp.status_code == 200
