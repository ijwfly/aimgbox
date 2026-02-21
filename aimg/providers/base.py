from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


class ProviderError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class AllProvidersFailedError(Exception):
    pass


@dataclass
class ProviderResult:
    output_data: bytes
    provider_job_id: str | None = None


class ProviderAdapter(ABC):
    def __init__(self, provider_id: UUID, config: dict | None = None) -> None:
        self.provider_id = provider_id
        self.config = config or {}

    @abstractmethod
    async def execute(
        self,
        input_data: bytes | None = None,
        params: dict | None = None,
    ) -> ProviderResult: ...
