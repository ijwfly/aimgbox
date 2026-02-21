from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from aimg.jobs.context import JobContext
from aimg.jobs.fields import OutputFile
from aimg.jobs.registry import job_handler
from aimg.providers.base import AllProvidersFailedError, ProviderError


class Txt2ImgInput(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    negative_prompt: str = ""
    width: int = Field(1024, ge=256, le=4096)
    height: int = Field(1024, ge=256, le=4096)
    output_format: Literal["png", "webp", "jpg"] = "png"


class Txt2ImgOutput(BaseModel):
    image: OutputFile

    model_config = {"arbitrary_types_allowed": True}


@job_handler(
    slug="txt2img",
    name="Text to Image",
    description="Generates an image from a text prompt using AI",
)
async def handle_txt2img(
    ctx: JobContext[Txt2ImgInput, Txt2ImgOutput],
) -> Txt2ImgOutput:
    for provider in ctx.providers:
        try:
            result = await provider.execute(
                params=ctx.input.model_dump(exclude_defaults=False),
            )
            return Txt2ImgOutput(
                image=OutputFile(
                    data=result.output_data,
                    content_type=f"image/{ctx.input.output_format}",
                )
            )
        except ProviderError as e:
            ctx.record_attempt(provider=provider, error=e)
            continue

    raise AllProvidersFailedError()
