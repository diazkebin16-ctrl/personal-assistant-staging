"""OpenTelemetry-compatible, content-free Orchestrator observation boundary."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class OrchestrationMetricEvent:
    name: str
    attributes: dict[str, str | int | float | bool]


class OrchestrationObserver(Protocol):
    def emit(self, event: OrchestrationMetricEvent) -> None: ...


class NullOrchestrationObserver:
    def emit(self, event: OrchestrationMetricEvent) -> None:
        del event
