import pytest


@pytest.mark.asyncio
async def test_list_job_types(client, seeded_data):
    headers = {"X-API-Key": seeded_data["token"]}
    resp = await client.get("/v1/meta/job-types", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    job_types = data["data"]["job_types"]
    slugs = [jt["slug"] for jt in job_types]
    assert "remove_bg" in slugs
    assert "txt2img" in slugs


@pytest.mark.asyncio
async def test_job_type_fields(client, seeded_data):
    headers = {"X-API-Key": seeded_data["token"]}
    resp = await client.get("/v1/meta/job-types", headers=headers)
    job_types = resp.json()["data"]["job_types"]

    for jt in job_types:
        assert "slug" in jt
        assert "name" in jt
        assert "description" in jt
        assert "credit_cost" in jt
        assert "input_schema" in jt
        assert "output_schema" in jt
        assert "timeout_seconds" in jt


@pytest.mark.asyncio
async def test_list_job_types_unauthenticated(client):
    resp = await client.get("/v1/meta/job-types")
    assert resp.status_code == 422 or resp.status_code == 401
