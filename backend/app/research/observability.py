"""Metadata-only Web Research observability."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ResearchMetricEvent:
    name: str
    attributes: dict[str, str | int | bool]


class ResearchObserver(Protocol):
    def emit(self, event: ResearchMetricEvent) -> None: ...


class NullResearchObserver:
    def emit(self, event: ResearchMetricEvent) -> None:
        del event
