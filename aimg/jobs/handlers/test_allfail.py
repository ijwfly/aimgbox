from __future__ import annotations

from aimg.jobs.context import JobContext
from aimg.jobs.fields import OutputFile
from aimg.jobs.handlers.remove_bg import RemoveBgInput, RemoveBgOutput
from aimg.jobs.registry import job_handler
from aimg.providers.base import AllProvidersFailedError, ProviderError


@job_handler(
    slug="test_allfail",
    name="Test All Fail",
    description="Test handler where all providers intentionally fail",
)
async def handle_test_allfail(
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
