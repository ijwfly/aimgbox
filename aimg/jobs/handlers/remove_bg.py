from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel

from aimg.jobs.context import JobContext
from aimg.jobs.fields import FileConstraints, InputFile, OutputFile
from aimg.jobs.registry import job_handler
from aimg.providers.base import AllProvidersFailedError, ProviderError


class RemoveBgInput(BaseModel):
    image: Annotated[InputFile, FileConstraints(max_size_mb=20, formats=["png", "jpg", "webp"])]
    output_format: Literal["png", "webp"] = "png"

    model_config = {"arbitrary_types_allowed": True}


class RemoveBgOutput(BaseModel):
    image: OutputFile

    model_config = {"arbitrary_types_allowed": True}


@job_handler(
    slug="remove_bg",
    name="Remove Background",
    description="Removes background from an image using AI",
)
async def handle_remove_bg(
    ctx: JobContext[RemoveBgInput, RemoveBgOutput],
) -> RemoveBgOutput:
    for provider in ctx.providers:
        try:
            result = await provider.execute(
                input_data=ctx.input.image.data,
                params={"output_format": ctx.input.output_format},
            )
            return RemoveBgOutput(
                image=OutputFile(
                    data=result.output_data,
                    content_type=f"image/{ctx.input.output_format}",
                )
            )
        except ProviderError as e:
            ctx.record_attempt(provider=provider, error=e)
            continue

    raise AllProvidersFailedError()
