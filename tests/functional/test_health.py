from aimg import __version__


async def test_health_returns_ok(client):
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["dependencies"]["database"] == "ok"
    assert body["dependencies"]["redis"] == "ok"
    assert body["dependencies"]["storage"] == "ok"

    assert "X-Request-ID" in response.headers
