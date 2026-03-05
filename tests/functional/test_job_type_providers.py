"""Tests for job_type_providers management (provider chain).

Spec reference: 04-database-schema.md — job_type_providers table
and 06-business-logic.md Section 16 — provider fallback chain.
"""
from aimg.db.repos.job_types import JobTypeRepo
from aimg.db.repos.providers import ProviderRepo


async def test_add_provider_to_job_type(db_pool):
    jt_repo = JobTypeRepo(db_pool)
    prov_repo = ProviderRepo(db_pool)

    jt = await jt_repo.upsert("jtp_test", "JTP Test", "Test", {}, {})
    provider = await prov_repo.create("jtp-prov", "JTP Prov", "mock.Class", "enc")

    jtp = await jt_repo.add_provider(jt.id, provider.id, priority=0)
    assert jtp.job_type_id == jt.id
    assert jtp.provider_id == provider.id
    assert jtp.priority == 0
    assert jtp.config_override == {}


async def test_provider_chain_ordering(db_pool):
    jt_repo = JobTypeRepo(db_pool)
    prov_repo = ProviderRepo(db_pool)

    jt = await jt_repo.upsert("jtp_order", "Order Test", "Test", {}, {})
    p1 = await prov_repo.create("jtp-p1", "P1", "mock.Class", "enc")
    p2 = await prov_repo.create("jtp-p2", "P2", "mock.Class", "enc")
    p3 = await prov_repo.create("jtp-p3", "P3", "mock.Class", "enc")

    await jt_repo.add_provider(jt.id, p3.id, priority=2)
    await jt_repo.add_provider(jt.id, p1.id, priority=0)
    await jt_repo.add_provider(jt.id, p2.id, priority=1)

    chain = await jt_repo.get_providers_for_job_type(jt.id)
    assert len(chain) == 3
    # Should be ordered by priority
    assert chain[0].provider_id == p1.id
    assert chain[1].provider_id == p2.id
    assert chain[2].provider_id == p3.id


async def test_remove_provider_from_chain(db_pool):
    jt_repo = JobTypeRepo(db_pool)
    prov_repo = ProviderRepo(db_pool)

    jt = await jt_repo.upsert("jtp_remove", "Remove Test", "Test", {}, {})
    p1 = await prov_repo.create("jtp-rm1", "RM1", "mock.Class", "enc")
    p2 = await prov_repo.create("jtp-rm2", "RM2", "mock.Class", "enc")

    await jt_repo.add_provider(jt.id, p1.id, priority=0)
    await jt_repo.add_provider(jt.id, p2.id, priority=1)

    removed = await jt_repo.remove_provider(jt.id, p1.id)
    assert removed is True

    chain = await jt_repo.get_providers_for_job_type(jt.id)
    assert len(chain) == 1
    assert chain[0].provider_id == p2.id


async def test_remove_nonexistent_provider(db_pool):
    jt_repo = JobTypeRepo(db_pool)
    jt = await jt_repo.upsert("jtp_noremove", "No Remove", "Test", {}, {})

    from uuid import uuid4
    removed = await jt_repo.remove_provider(jt.id, uuid4())
    assert removed is False


async def test_add_provider_with_config_override(db_pool):
    jt_repo = JobTypeRepo(db_pool)
    prov_repo = ProviderRepo(db_pool)

    jt = await jt_repo.upsert("jtp_config", "Config Test", "Test", {}, {})
    provider = await prov_repo.create("jtp-cfg", "CFG", "mock.Class", "enc")

    jtp = await jt_repo.add_provider(
        jt.id, provider.id, priority=0,
        config_override={"model": "v2", "version": "abc123"},
    )
    assert jtp.config_override == {"model": "v2", "version": "abc123"}


async def test_upsert_provider_updates_priority(db_pool):
    """Adding same provider again should update priority and config."""
    jt_repo = JobTypeRepo(db_pool)
    prov_repo = ProviderRepo(db_pool)

    jt = await jt_repo.upsert("jtp_upsert", "Upsert Test", "Test", {}, {})
    provider = await prov_repo.create("jtp-ups", "UPS", "mock.Class", "enc")

    await jt_repo.add_provider(jt.id, provider.id, priority=0)
    await jt_repo.add_provider(jt.id, provider.id, priority=5)

    chain = await jt_repo.get_providers_for_job_type(jt.id)
    assert len(chain) == 1  # Not duplicated
    assert chain[0].priority == 5


async def test_empty_provider_chain(db_pool):
    jt_repo = JobTypeRepo(db_pool)
    jt = await jt_repo.upsert("jtp_empty", "Empty Test", "Test", {}, {})

    chain = await jt_repo.get_providers_for_job_type(jt.id)
    assert chain == []


async def test_job_type_update_credit_cost_and_timeout(db_pool):
    """Test updating job type credit_cost and timeout_seconds."""
    jt_repo = JobTypeRepo(db_pool)
    jt = await jt_repo.upsert("jtp_update", "Update Test", "Test", {}, {})
    assert jt.credit_cost == 1  # default

    updated = await jt_repo.update(jt.id, credit_cost=5, timeout_seconds=300)
    assert updated.credit_cost == 5
    assert updated.timeout_seconds == 300


async def test_job_type_update_status(db_pool):
    jt_repo = JobTypeRepo(db_pool)
    jt = await jt_repo.upsert("jtp_status", "Status Test", "Test", {}, {})
    assert jt.status == "active"

    updated = await jt_repo.update(jt.id, status="disabled")
    assert updated.status == "disabled"
