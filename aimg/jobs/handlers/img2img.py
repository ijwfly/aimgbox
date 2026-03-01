from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from aimg.jobs.context import JobContext
from aimg.jobs.fields import FileConstraints, InputFile, OutputFile
from aimg.jobs.registry import job_handler
from aimg.providers.base import AllProvidersFailedError, ProviderError


class Img2ImgInput(BaseModel):
    image: Annotated[InputFile, FileConstraints(max_size_mb=20, formats=["png", "jpg", "webp"])]
    prompt: str = Field(min_length=1, max_length=2000)
    output_format: Literal["png", "webp", "jpg"] = "png"

    model_config = {"arbitrary_types_allowed": True}


class Img2ImgOutput(BaseModel):
    image: OutputFile

    model_config = {"arbitrary_types_allowed": True}


@job_handler(
    slug="img2img",
    name="Image to Image",
    description="Edits an image based on a text prompt using AI",
)
async def handle_img2img(
    ctx: JobContext[Img2ImgInput, Img2ImgOutput],
) -> Img2ImgOutput:
    for provider in ctx.providers:
        try:
            result = await provider.execute(
                input_data=ctx.input.image.data,
                params={"prompt": ctx.input.prompt},
            )
            return Img2ImgOutput(
                image=OutputFile(
                    data=result.output_data,
                    content_type=f"image/{ctx.input.output_format}",
                )
            )
        except ProviderError as e:
            ctx.record_attempt(provider=provider, error=e)
            continue

    raise AllProvidersFailedError()
