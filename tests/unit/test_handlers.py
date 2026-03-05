import pytest
from uuid import uuid4
from unittest.mock import MagicMock

from aimg.jobs.context import JobContext
from aimg.jobs.fields import InputFile, OutputFile
from aimg.providers.base import AllProvidersFailedError, ProviderError, ProviderResult
from aimg.providers.mock import MockProvider
from aimg.providers.failing_mock import FailingMockProvider
from aimg.jobs.handlers.remove_bg import RemoveBgInput, RemoveBgOutput, handle_remove_bg
from aimg.jobs.handlers.txt2img import Txt2ImgInput, Txt2ImgOutput, handle_txt2img


def _make_input_file(data=b"image-bytes"):
    return InputFile(
        file_id=uuid4(),
        data=data,
        content_type="image/png",
        original_filename="test.png",
        size_bytes=len(data),
    )


@pytest.mark.asyncio
async def test_remove_bg_success():
    provider = MockProvider(provider_id=uuid4())
    input_file = _make_input_file(b"original-image")
    typed_input = RemoveBgInput(image=input_file, output_format="png")

    ctx = JobContext(
        job_id=uuid4(),
        input=typed_input,
        providers=[provider],
        language="en",
        logger=MagicMock(),
    )

    result = await handle_remove_bg(ctx)
    assert isinstance(result, RemoveBgOutput)
    assert isinstance(result.image, OutputFile)
    assert result.image.data == b"original-image"
    assert result.image.content_type == "image/png"


@pytest.mark.asyncio
async def test_remove_bg_webp_output():
    provider = MockProvider(provider_id=uuid4())
    input_file = _make_input_file(b"image-data")
    typed_input = RemoveBgInput(image=input_file, output_format="webp")

    ctx = JobContext(
        job_id=uuid4(),
        input=typed_input,
        providers=[provider],
        language="en",
        logger=MagicMock(),
    )

    result = await handle_remove_bg(ctx)
    assert result.image.content_type == "image/webp"


@pytest.mark.asyncio
async def test_remove_bg_all_providers_fail():
    p1 = FailingMockProvider(provider_id=uuid4())
    p2 = FailingMockProvider(provider_id=uuid4())
    input_file = _make_input_file()
    typed_input = RemoveBgInput(image=input_file)

    ctx = JobContext(
        job_id=uuid4(),
        input=typed_input,
        providers=[p1, p2],
        language="en",
        logger=MagicMock(),
    )

    with pytest.raises(AllProvidersFailedError):
        await handle_remove_bg(ctx)

    assert len(ctx._attempts) == 2


@pytest.mark.asyncio
async def test_remove_bg_fallback_to_second_provider():
    failing = FailingMockProvider(provider_id=uuid4())
    working = MockProvider(provider_id=uuid4())
    input_file = _make_input_file(b"my-image")
    typed_input = RemoveBgInput(image=input_file)

    ctx = JobContext(
        job_id=uuid4(),
        input=typed_input,
        providers=[failing, working],
        language="en",
        logger=MagicMock(),
    )

    result = await handle_remove_bg(ctx)
    assert result.image.data == b"my-image"
    assert len(ctx._attempts) == 1  # one failure recorded


@pytest.mark.asyncio
async def test_txt2img_success():
    provider = MockProvider(provider_id=uuid4())
    typed_input = Txt2ImgInput(prompt="A sunset")

    ctx = JobContext(
        job_id=uuid4(),
        input=typed_input,
        providers=[provider],
        language="en",
        logger=MagicMock(),
    )

    result = await handle_txt2img(ctx)
    assert isinstance(result, Txt2ImgOutput)
    assert isinstance(result.image, OutputFile)
    assert result.image.content_type == "image/png"
    assert result.image.data[:4] == b"\x89PNG"


@pytest.mark.asyncio
async def test_txt2img_custom_format():
    provider = MockProvider(provider_id=uuid4())
    typed_input = Txt2ImgInput(prompt="Mountains", output_format="webp")

    ctx = JobContext(
        job_id=uuid4(),
        input=typed_input,
        providers=[provider],
        language="ru",
        logger=MagicMock(),
    )

    result = await handle_txt2img(ctx)
    assert result.image.content_type == "image/webp"


@pytest.mark.asyncio
async def test_txt2img_all_providers_fail():
    p1 = FailingMockProvider(provider_id=uuid4())
    typed_input = Txt2ImgInput(prompt="Test")

    ctx = JobContext(
        job_id=uuid4(),
        input=typed_input,
        providers=[p1],
        language="en",
        logger=MagicMock(),
    )

    with pytest.raises(AllProvidersFailedError):
        await handle_txt2img(ctx)

    assert len(ctx._attempts) == 1


@pytest.mark.asyncio
async def test_txt2img_fallback():
    failing = FailingMockProvider(provider_id=uuid4())
    working = MockProvider(provider_id=uuid4())
    typed_input = Txt2ImgInput(prompt="Hello world", width=512, height=512)

    ctx = JobContext(
        job_id=uuid4(),
        input=typed_input,
        providers=[failing, working],
        language="en",
        logger=MagicMock(),
    )

    result = await handle_txt2img(ctx)
    assert isinstance(result, Txt2ImgOutput)
    assert len(ctx._attempts) == 1


def test_txt2img_input_validation_min_length():
    with pytest.raises(Exception):
        Txt2ImgInput(prompt="")


def test_txt2img_input_default_values():
    inp = Txt2ImgInput(prompt="Test prompt")
    assert inp.width == 1024
    assert inp.height == 1024
    assert inp.output_format == "png"
    assert inp.negative_prompt == ""
