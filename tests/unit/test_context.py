import pytest
from uuid import uuid4
from unittest.mock import MagicMock

from aimg.jobs.context import JobContext, AttemptRecord
from aimg.providers.base import ProviderError, ProviderAdapter


def test_attempt_record_creation():
    pid = uuid4()
    record = AttemptRecord(
        provider_id=pid,
        error_code="ERR",
        error_message="Something failed",
    )
    assert record.provider_id == pid
    assert record.error_code == "ERR"
    assert record.error_message == "Something failed"


def test_job_context_record_attempt():
    pid = uuid4()
    provider = MagicMock(spec=ProviderAdapter)
    provider.provider_id = pid

    logger = MagicMock()

    ctx = JobContext(
        job_id=uuid4(),
        input={"test": True},
        providers=[provider],
        language="en",
        logger=logger,
    )

    error = ProviderError("TIMEOUT", "Provider timed out")
    ctx.record_attempt(provider, error)

    assert len(ctx._attempts) == 1
    assert ctx._attempts[0].provider_id == pid
    assert ctx._attempts[0].error_code == "TIMEOUT"
    assert ctx._attempts[0].error_message == "Provider timed out"
    logger.warning.assert_called_once()


def test_job_context_multiple_attempts():
    logger = MagicMock()

    p1 = MagicMock(spec=ProviderAdapter)
    p1.provider_id = uuid4()
    p2 = MagicMock(spec=ProviderAdapter)
    p2.provider_id = uuid4()

    ctx = JobContext(
        job_id=uuid4(),
        input={},
        providers=[p1, p2],
        language="ru",
        logger=logger,
    )

    ctx.record_attempt(p1, ProviderError("ERR1", "First"))
    ctx.record_attempt(p2, ProviderError("ERR2", "Second"))

    assert len(ctx._attempts) == 2
    assert ctx._attempts[0].error_code == "ERR1"
    assert ctx._attempts[1].error_code == "ERR2"


def test_job_context_empty_attempts():
    ctx = JobContext(
        job_id=uuid4(),
        input={},
        providers=[],
        language="en",
        logger=MagicMock(),
    )
    assert ctx._attempts == []
