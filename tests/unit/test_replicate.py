from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from aimg.providers.base import ProviderError
from aimg.providers.replicate import ReplicateAdapter


def _make_adapter(**config_overrides):
    config = {
        "api_key": "test-key",
        "model": "test/model",
        "version": "abc123",
        "base_url": "https://api.replicate.com/v1",
        **config_overrides,
    }
    return ReplicateAdapter(provider_id=uuid4(), config=config)


def _mock_response(status_code=201, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = ""
    return resp


@pytest.mark.asyncio
async def test_success_flow():
    adapter = _make_adapter()

    create_resp = _mock_response(201, {"id": "pred-1", "status": "starting"})
    poll_resp = _mock_response(200, {
        "id": "pred-1",
        "status": "succeeded",
        "output": ["https://example.com/output.png"],
    })
    download_resp = MagicMock()
    download_resp.content = b"fake-image-bytes"
    download_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=create_resp)
    mock_client.get = AsyncMock(side_effect=[poll_resp, download_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("aimg.providers.replicate.httpx.AsyncClient", return_value=mock_client),
        patch("aimg.providers.replicate.asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await adapter.execute(params={"prompt": "a cat"})

    assert result.output_data == b"fake-image-bytes"
    assert result.provider_job_id == "pred-1"


@pytest.mark.asyncio
async def test_failed_prediction():
    adapter = _make_adapter()

    create_resp = _mock_response(201, {"id": "pred-2", "status": "starting"})
    poll_resp = _mock_response(200, {
        "id": "pred-2",
        "status": "failed",
        "error": "Model crashed",
    })

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=create_resp)
    mock_client.get = AsyncMock(return_value=poll_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("aimg.providers.replicate.httpx.AsyncClient", return_value=mock_client),
        patch("aimg.providers.replicate.asyncio.sleep", new_callable=AsyncMock),
    ):
        with pytest.raises(ProviderError) as exc_info:
            await adapter.execute(params={"prompt": "test"})
    assert exc_info.value.code == "PREDICTION_FAILED"


@pytest.mark.asyncio
async def test_api_error_on_create():
    adapter = _make_adapter()

    create_resp = _mock_response(500, {})
    create_resp.text = "Internal Server Error"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=create_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("aimg.providers.replicate.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ProviderError) as exc_info:
            await adapter.execute(params={"prompt": "test"})
    assert exc_info.value.code == "API_ERROR"


@pytest.mark.asyncio
async def test_input_data_to_base64():
    adapter = _make_adapter()

    create_resp = _mock_response(201, {"id": "pred-3", "status": "starting"})
    poll_resp = _mock_response(200, {
        "id": "pred-3",
        "status": "succeeded",
        "output": "https://example.com/out.png",
    })
    download_resp = MagicMock()
    download_resp.content = b"output-bytes"
    download_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=create_resp)
    mock_client.get = AsyncMock(side_effect=[poll_resp, download_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("aimg.providers.replicate.httpx.AsyncClient", return_value=mock_client),
        patch("aimg.providers.replicate.asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await adapter.execute(
            input_data=b"\x89PNG\r\n\x1a\nfake",
            params={"output_format": "png"},
        )

    # Verify the POST body included base64 image
    call_args = mock_client.post.call_args
    body = call_args.kwargs["json"]
    assert "image" in body["input"]
    assert body["input"]["image"].startswith("data:")
    assert result.output_data == b"output-bytes"


@pytest.mark.asyncio
async def test_params_only_no_input_data():
    adapter = _make_adapter()

    create_resp = _mock_response(201, {"id": "pred-4", "status": "starting"})
    poll_resp = _mock_response(200, {
        "id": "pred-4",
        "status": "succeeded",
        "output": ["https://example.com/gen.png"],
    })
    download_resp = MagicMock()
    download_resp.content = b"generated"
    download_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=create_resp)
    mock_client.get = AsyncMock(side_effect=[poll_resp, download_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("aimg.providers.replicate.httpx.AsyncClient", return_value=mock_client),
        patch("aimg.providers.replicate.asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await adapter.execute(params={"prompt": "a dog", "width": 512})

    call_args = mock_client.post.call_args
    body = call_args.kwargs["json"]
    assert "image" not in body["input"]
    assert body["input"]["prompt"] == "a dog"
    assert result.output_data == b"generated"
