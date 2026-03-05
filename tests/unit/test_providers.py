import pytest
from uuid import uuid4

from aimg.providers.base import ProviderAdapter, ProviderError, ProviderResult, AllProvidersFailedError
from aimg.providers.mock import MockProvider
from aimg.providers.failing_mock import FailingMockProvider


def test_provider_result_dataclass():
    result = ProviderResult(output_data=b"test", provider_job_id="job-1")
    assert result.output_data == b"test"
    assert result.provider_job_id == "job-1"


def test_provider_result_optional_job_id():
    result = ProviderResult(output_data=b"data")
    assert result.provider_job_id is None


def test_provider_error_attributes():
    err = ProviderError("ERR_CODE", "Something went wrong")
    assert err.code == "ERR_CODE"
    assert err.message == "Something went wrong"
    assert str(err) == "Something went wrong"


def test_all_providers_failed_error():
    err = AllProvidersFailedError()
    assert isinstance(err, Exception)


@pytest.mark.asyncio
async def test_mock_provider_returns_input_data():
    provider = MockProvider(provider_id=uuid4())
    result = await provider.execute(input_data=b"hello world")
    assert result.output_data == b"hello world"
    assert result.provider_job_id == "mock-001"


@pytest.mark.asyncio
async def test_mock_provider_returns_png_without_input():
    provider = MockProvider(provider_id=uuid4())
    result = await provider.execute()
    assert result.output_data[:4] == b"\x89PNG"
    assert result.provider_job_id == "mock-001"


@pytest.mark.asyncio
async def test_mock_provider_with_params():
    provider = MockProvider(provider_id=uuid4())
    result = await provider.execute(params={"key": "val"})
    assert result.output_data[:4] == b"\x89PNG"


@pytest.mark.asyncio
async def test_failing_mock_raises_provider_error():
    provider = FailingMockProvider(provider_id=uuid4())
    with pytest.raises(ProviderError) as exc_info:
        await provider.execute()
    assert exc_info.value.code == "MOCK_FAIL"
    assert exc_info.value.message == "Intentional failure"


@pytest.mark.asyncio
async def test_failing_mock_with_input_still_fails():
    provider = FailingMockProvider(provider_id=uuid4())
    with pytest.raises(ProviderError):
        await provider.execute(input_data=b"data", params={"key": "val"})


def test_provider_adapter_stores_config():
    pid = uuid4()
    adapter = MockProvider(provider_id=pid, config={"api_key": "secret"})
    assert adapter.provider_id == pid
    assert adapter.config == {"api_key": "secret"}


def test_provider_adapter_default_config():
    adapter = MockProvider(provider_id=uuid4())
    assert adapter.config == {}
