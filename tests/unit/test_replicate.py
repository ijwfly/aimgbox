from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from aimg.providers.base import ProviderError
from aimg.providers.replicate import ReplicateAdapter, _detect_mime_type


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


# ── _detect_mime_type tests ────────────────────────────────────


def test_detect_mime_type_png():
    assert _detect_mime_type(b"\x89PNG\r\n\x1a\nrest") == "image/png"


def test_detect_mime_type_jpeg():
    assert _detect_mime_type(b"\xff\xd8\xffrest") == "image/jpeg"


def test_detect_mime_type_webp():
    data = b"RIFF\x00\x00\x00\x00WEBPrest"
    assert _detect_mime_type(data) == "image/webp"


def test_detect_mime_type_unknown():
    assert _detect_mime_type(b"\x00\x00\x00\x00") == "application/octet-stream"


# ── Model-based endpoint (no version) ─────────────────────────


@pytest.mark.asyncio
async def test_model_based_endpoint():
    """When model is set and version is empty, use /models/{model}/predictions."""
    adapter = _make_adapter(version="")

    create_resp = _mock_response(201, {
        "id": "pred-m1",
        "status": "starting",
        "urls": {"get": "https://api.replicate.com/v1/predictions/pred-m1"},
    })
    poll_resp = _mock_response(200, {
        "id": "pred-m1",
        "status": "succeeded",
        "output": ["https://example.com/output.png"],
    })
    download_resp = MagicMock()
    download_resp.content = b"model-output"
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
        result = await adapter.execute(params={"prompt": "test"})

    # Verify URL uses model-based endpoint
    call_args = mock_client.post.call_args
    assert "/models/test/model/predictions" in call_args.args[0]
    # Body should NOT have "version" key
    body = call_args.kwargs["json"]
    assert "version" not in body
    assert body["input"]["prompt"] == "test"
    assert result.output_data == b"model-output"


# ── Sync mode ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_mode():
    """Sync mode adds Prefer: wait header and returns immediately on succeeded."""
    adapter = _make_adapter(version="", sync_mode=True)

    create_resp = _mock_response(201, {
        "id": "pred-sync",
        "status": "succeeded",
        "output": "https://example.com/sync-out.png",
    })
    download_resp = MagicMock()
    download_resp.content = b"sync-output"
    download_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=create_resp)
    mock_client.get = AsyncMock(return_value=download_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("aimg.providers.replicate.httpx.AsyncClient", return_value=mock_client):
        result = await adapter.execute(params={"test": "val"})

    # Verify Prefer: wait header
    call_args = mock_client.post.call_args
    assert call_args.kwargs["headers"]["Prefer"] == "wait"
    # Should download output without polling (only 1 GET for download)
    assert mock_client.get.call_count == 1
    assert result.output_data == b"sync-output"
    assert result.provider_job_id == "pred-sync"


# ── input_as_array ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_input_as_array():
    """input_as_array wraps the data URI in a list."""
    adapter = _make_adapter(version="", input_field="images", input_as_array=True)

    create_resp = _mock_response(201, {
        "id": "pred-arr",
        "status": "starting",
        "urls": {"get": "https://api.replicate.com/v1/predictions/pred-arr"},
    })
    poll_resp = _mock_response(200, {
        "id": "pred-arr",
        "status": "succeeded",
        "output": ["https://example.com/arr-out.png"],
    })
    download_resp = MagicMock()
    download_resp.content = b"arr-output"
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
            input_data=b"\x89PNG\r\n\x1a\ntest",
            params={"prompt": "edit"},
        )

    body = mock_client.post.call_args.kwargs["json"]
    images_val = body["input"]["images"]
    assert isinstance(images_val, list)
    assert len(images_val) == 1
    assert images_val[0].startswith("data:image/png;base64,")
    assert "image" not in body["input"]  # field is "images", not "image"
    assert result.output_data == b"arr-output"


# ── exclude_params ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exclude_params():
    """exclude_params strips specified keys from prediction input."""
    adapter = _make_adapter(version="", exclude_params=["output_format", "internal_flag"])

    create_resp = _mock_response(201, {
        "id": "pred-excl",
        "status": "starting",
        "urls": {"get": "https://api.replicate.com/v1/predictions/pred-excl"},
    })
    poll_resp = _mock_response(200, {
        "id": "pred-excl",
        "status": "succeeded",
        "output": "https://example.com/excl-out.png",
    })
    download_resp = MagicMock()
    download_resp.content = b"excl-output"
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
            params={"prompt": "keep", "output_format": "png", "internal_flag": True},
        )

    body = mock_client.post.call_args.kwargs["json"]
    assert body["input"]["prompt"] == "keep"
    assert "output_format" not in body["input"]
    assert "internal_flag" not in body["input"]
    assert result.output_data == b"excl-output"


# ── default_params ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_default_params():
    """default_params are merged but overridden by handler params."""
    adapter = _make_adapter(
        version="",
        default_params={"aspect_ratio": "match_input_image", "quality": "high"},
    )

    create_resp = _mock_response(201, {
        "id": "pred-def",
        "status": "starting",
        "urls": {"get": "https://api.replicate.com/v1/predictions/pred-def"},
    })
    poll_resp = _mock_response(200, {
        "id": "pred-def",
        "status": "succeeded",
        "output": "https://example.com/def-out.png",
    })
    download_resp = MagicMock()
    download_resp.content = b"def-output"
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
            params={"prompt": "test", "quality": "low"},  # override default
        )

    body = mock_client.post.call_args.kwargs["json"]
    assert body["input"]["aspect_ratio"] == "match_input_image"  # from defaults
    assert body["input"]["quality"] == "low"  # overridden by handler params
    assert body["input"]["prompt"] == "test"
    assert result.output_data == b"def-output"
