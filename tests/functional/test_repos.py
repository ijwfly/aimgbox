
from aimg.db.repos.api_keys import ApiKeyRepo
from aimg.db.repos.credit_transactions import CreditTransactionRepo
from aimg.db.repos.files import FileRepo
from aimg.db.repos.integrations import IntegrationRepo
from aimg.db.repos.job_types import JobTypeRepo
from aimg.db.repos.jobs import JobRepo
from aimg.db.repos.partners import PartnerRepo
from aimg.db.repos.providers import ProviderRepo
from aimg.db.repos.users import UserRepo


async def test_partner_crud(db_pool):
    repo = PartnerRepo(db_pool)
    p = await repo.create("ACME Corp")
    assert p.name == "ACME Corp"
    assert p.status == "active"

    loaded = await repo.get_by_id(p.id)
    assert loaded is not None
    assert loaded.name == "ACME Corp"


async def test_integration_crud(db_pool):
    partner = await PartnerRepo(db_pool).create("Test")
    repo = IntegrationRepo(db_pool)
    integ = await repo.create(partner.id, "My App", default_free_credits=5)
    assert integ.name == "My App"
    assert integ.default_free_credits == 5

    loaded = await repo.get_by_id(integ.id)
    assert loaded is not None


async def test_api_key_crud(db_pool):
    partner = await PartnerRepo(db_pool).create("Test")
    integ = await IntegrationRepo(db_pool).create(partner.id, "App")
    repo = ApiKeyRepo(db_pool)

    key = await repo.create(integ.id, "hash123", label="primary")
    assert key.key_hash == "hash123"
    assert key.is_revoked is False

    by_hash = await repo.get_by_hash("hash123")
    assert by_hash is not None
    assert by_hash.id == key.id


async def test_user_get_or_create(db_pool):
    partner = await PartnerRepo(db_pool).create("Test")
    integ = await IntegrationRepo(db_pool).create(partner.id, "App")
    repo = UserRepo(db_pool)

    user1 = await repo.get_or_create(integ.id, "ext-user-1", default_free_credits=10)
    assert user1.external_user_id == "ext-user-1"
    assert user1.free_credits == 10

    user2 = await repo.get_or_create(integ.id, "ext-user-1")
    assert user2.id == user1.id  # same user returned


async def test_user_update_credits(db_pool):
    partner = await PartnerRepo(db_pool).create("Test")
    integ = await IntegrationRepo(db_pool).create(partner.id, "App")
    repo = UserRepo(db_pool)

    user = await repo.get_or_create(integ.id, "ext-1", default_free_credits=10)
    updated = await repo.update_credits(user.id, -3, 0)
    assert updated is True

    user = await repo.get_by_id(user.id)
    assert user.free_credits == 7

    # Cannot go negative
    result = await repo.update_credits(user.id, -100, 0)
    assert result is False


async def test_provider_crud(db_pool):
    repo = ProviderRepo(db_pool)
    p = await repo.create("test-prov", "Test Provider", "some.Class", "enc-key")
    assert p.slug == "test-prov"

    by_slug = await repo.get_by_slug("test-prov")
    assert by_slug.id == p.id


async def test_job_type_upsert(db_pool):
    repo = JobTypeRepo(db_pool)
    jt = await repo.upsert("test_job", "Test Job", "desc", {}, {})
    assert jt.slug == "test_job"
    assert jt.credit_cost == 1  # default

    jt2 = await repo.upsert("test_job", "Test Job Updated", "new desc", {"a": 1}, {})
    assert jt2.id == jt.id
    assert jt2.name == "Test Job Updated"


async def test_file_crud(db_pool):
    partner = await PartnerRepo(db_pool).create("Test")
    integ = await IntegrationRepo(db_pool).create(partner.id, "App")
    repo = FileRepo(db_pool)

    f = await repo.create(
        integ.id, None, "bucket", "key.png", "image/png", 1024, "input",
        original_filename="photo.png",
    )
    assert f.purpose == "input"

    loaded = await repo.get_by_id(f.id)
    assert loaded is not None
    assert loaded.original_filename == "photo.png"


async def test_job_crud(db_pool):
    partner = await PartnerRepo(db_pool).create("Test")
    integ = await IntegrationRepo(db_pool).create(partner.id, "App")
    user = await UserRepo(db_pool).get_or_create(integ.id, "u1")
    jt = await JobTypeRepo(db_pool).upsert("test", "Test", None, {}, {})
    repo = JobRepo(db_pool)

    job = await repo.create(integ.id, user.id, jt.id, {"key": "val"}, 1)
    assert job.status == "pending"
    assert job.input_data == {"key": "val"}

    loaded = await repo.get_by_id(job.id)
    assert loaded is not None


async def test_credit_transaction_crud(db_pool):
    partner = await PartnerRepo(db_pool).create("Test")
    integ = await IntegrationRepo(db_pool).create(partner.id, "App")
    user = await UserRepo(db_pool).get_or_create(integ.id, "u1", default_free_credits=10)
    jt = await JobTypeRepo(db_pool).upsert("test", "Test", None, {}, {})
    job = await JobRepo(db_pool).create(integ.id, user.id, jt.id, {}, 1)

    repo = CreditTransactionRepo(db_pool)
    ct = await repo.create(user.id, -1, "free", "job_charge", 9, job_id=job.id)
    assert ct.amount == -1

    charges = await repo.get_charges_for_job(job.id)
    assert len(charges) == 1
    assert charges[0].id == ct.id
