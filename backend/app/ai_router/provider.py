"""Minimal provider protocol, immutable registry, and deterministic test adapter."""

import asyncio
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from backend.app.ai_router.enums import FailureCategory, is_retryable_failure
from backend.app.ai_router.schemas import ProviderRequest, ProviderResponse


class ProviderFailure(Exception):
    """Safe classified provider failure; raw provider responses are never included."""

    def __init__(self, category: FailureCategory) -> None:
        super().__init__(f"Provider request failed: {category.value}")
        self.category = category
        self.retryable = is_retryable_failure(category)


@runtime_checkable
class LLMProvider(Protocol):
    """Provider-neutral text generation boundary used by Phase 5."""

    @property
    def key(self) -> str: ...

    async def generate(self, model_id: str, request: ProviderRequest) -> ProviderResponse: ...


class ProviderRegistry:
    """Server-constructed adapter registry with no request-time mutation surface."""

    def __init__(self, providers: Iterable[LLMProvider]) -> None:
        provider_map: dict[str, LLMProvider] = {}
        for provider in providers:
            if provider.key in provider_map:
                raise ValueError(f"Duplicate provider adapter: {provider.key}")
            provider_map[provider.key] = provider
        self._providers = provider_map

    def get(self, provider_key: str) -> LLMProvider:
        try:
            return self._providers[provider_key]
        except KeyError:
            raise ProviderFailure(FailureCategory.PROVIDER_UNAVAILABLE) from None


class FakeProvider:
    """Deterministic no-network adapter for interface and fallback tests."""

    def __init__(
        self,
        key: str,
        outcomes: Iterable[ProviderResponse | FailureCategory],
    ) -> None:
        self._key = key
        self._outcomes = tuple(outcomes)
        self._index = 0
        self._lock = asyncio.Lock()

    @property
    def key(self) -> str:
        return self._key

    @property
    def call_count(self) -> int:
        return self._index

    async def generate(self, model_id: str, request: ProviderRequest) -> ProviderResponse:
        del model_id, request
        async with self._lock:
            if self._index >= len(self._outcomes):
                raise ProviderFailure(FailureCategory.PROVIDER_UNAVAILABLE)
            outcome = self._outcomes[self._index]
            self._index += 1
        if isinstance(outcome, FailureCategory):
            raise ProviderFailure(outcome)
        return outcome
