from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar
from uuid import UUID

import structlog

from aimg.providers.base import ProviderAdapter, ProviderError

TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


@dataclass
class AttemptRecord:
    provider_id: UUID
    error_code: str
    error_message: str


@dataclass
class JobContext(Generic[TInput, TOutput]):  # noqa: UP046
    job_id: UUID
    input: TInput
    providers: list[ProviderAdapter]
    language: str
    logger: structlog.stdlib.BoundLogger

    _attempts: list[AttemptRecord] = field(default_factory=list)

    def record_attempt(self, provider: ProviderAdapter, error: ProviderError) -> None:
        self._attempts.append(
            AttemptRecord(
                provider_id=provider.provider_id,
                error_code=error.code,
                error_message=error.message,
            )
        )
        self.logger.warning(
            "provider_attempt_failed",
            provider_id=str(provider.provider_id),
            error_code=error.code,
            error_message=error.message,
        )
