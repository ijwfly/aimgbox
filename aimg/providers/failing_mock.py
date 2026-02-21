from aimg.providers.base import ProviderAdapter, ProviderError, ProviderResult


class FailingMockProvider(ProviderAdapter):
    async def execute(
        self,
        input_data: bytes | None = None,
        params: dict | None = None,
    ) -> ProviderResult:
        raise ProviderError("MOCK_FAIL", "Intentional failure")
