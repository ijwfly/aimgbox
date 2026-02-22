async def test_dashboard(admin_client):
    resp = await admin_client.get("/admin/dashboard")
    assert resp.status_code == 200
    assert "Dashboard" in resp.text
    assert "Active Jobs" in resp.text


async def test_dashboard_redirect(admin_client):
    resp = await admin_client.get("/admin/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/admin/dashboard" in resp.headers["location"]
