from aimg.db.repos.integrations import IntegrationRepo
from aimg.db.repos.job_types import JobTypeRepo
from aimg.db.repos.jobs import JobRepo
from aimg.db.repos.partners import PartnerRepo
from aimg.db.repos.providers import ProviderRepo
from aimg.db.repos.users import UserRepo


async def _create_job(db_pool):
    partner = await PartnerRepo(db_pool).create("JobPartner")
    integration = await IntegrationRepo(db_pool).create(partner.id, "JobInt")
    user = await UserRepo(db_pool).get_or_create(
        integration.id, "job-user", default_free_credits=10,
    )
    provider = await ProviderRepo(db_pool).create(
        slug="mockjob", name="Mock Job", adapter_class="mock",
        api_key_encrypted="none",
    )
    jt = await JobTypeRepo(db_pool).upsert(
        slug="test_job", name="Test Job", description="test",
        input_schema={}, output_schema={},
    )
    await JobTypeRepo(db_pool).add_provider(jt.id, provider.id)
    job = await JobRepo(db_pool).create(
        integration.id, user.id, jt.id, {"test": True}, 1,
    )
    return job


async def test_job_list(admin_client, db_pool):
    await _create_job(db_pool)

    resp = await admin_client.get("/admin/jobs")
    assert resp.status_code == 200
    assert "Jobs" in resp.text


async def test_job_detail(admin_client, db_pool):
    job = await _create_job(db_pool)

    resp = await admin_client.get(f"/admin/jobs/{job.id}")
    assert resp.status_code == 200
    assert "Job Details" in resp.text


async def test_job_export_csv(admin_client, db_pool):
    await _create_job(db_pool)

    resp = await admin_client.get("/admin/jobs/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/csv; charset=utf-8"
    assert "attachment" in resp.headers["content-disposition"]
    assert "id,status" in resp.text


async def test_job_list_with_filters(admin_client, db_pool):
    await _create_job(db_pool)

    resp = await admin_client.get("/admin/jobs?status=pending")
    assert resp.status_code == 200
