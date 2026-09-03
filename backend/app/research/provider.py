"""Provider abstraction with explicit test-only adapter rejection in production."""

import asyncio
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from backend.app.core.config import Environment
from backend.app.research.enums import ResearchErrorCode
from backend.app.research.errors import ResearchError
from backend.app.research.schemas import SearchResult


@runtime_checkable
class SearchProvider(Protocol):
    @property
    def key(self) -> str: ...

    @property
    def test_only(self) -> bool: ...

    async def search(self, query: str, limit: int) -> tuple[SearchResult, ...]: ...


class SearchProviderRegistry:
    def __init__(self, providers: Iterable[SearchProvider], *, environment: Environment) -> None:
        self._providers: dict[str, SearchProvider] = {}
        for provider in providers:
            if provider.key in self._providers:
                raise ValueError(f"Duplicate search provider: {provider.key}")
            if environment is Environment.PRODUCTION and provider.test_only:
                raise ValueError("Test-only search providers are forbidden in production")
            self._providers[provider.key] = provider

    def default(self) -> SearchProvider:
        if not self._providers:
            raise ResearchError(ResearchErrorCode.PROVIDER_UNAVAILABLE)
        return self._providers[sorted(self._providers)[0]]


class FakeSearchProvider:
    """Deterministic no-network test adapter; impossible to register in production."""

    test_only = True

    def __init__(
        self,
        outcomes: Iterable[tuple[SearchResult, ...] | ResearchErrorCode],
        *,
        key: str = "fake-search",
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

    async def search(self, query: str, limit: int) -> tuple[SearchResult, ...]:
        del query
        async with self._lock:
            if self._index >= len(self._outcomes):
                raise ResearchError(ResearchErrorCode.PROVIDER_UNAVAILABLE)
            outcome = self._outcomes[self._index]
            self._index += 1
        if isinstance(outcome, ResearchErrorCode):
            raise ResearchError(outcome)
        return outcome[:limit]
