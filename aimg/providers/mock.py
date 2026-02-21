from aimg.providers.base import ProviderAdapter, ProviderResult

# Minimal 1x1 transparent PNG
_TRANSPARENT_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class MockProvider(ProviderAdapter):
    async def execute(
        self,
        input_data: bytes | None = None,
        params: dict | None = None,
    ) -> ProviderResult:
        output = input_data if input_data else _TRANSPARENT_PNG
        return ProviderResult(output_data=output, provider_job_id="mock-001")
