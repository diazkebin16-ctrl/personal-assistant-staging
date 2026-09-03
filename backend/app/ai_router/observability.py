"""OpenTelemetry-ready event boundary without a collector dependency."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AIRoutingMetricEvent:
    """Privacy-safe metric/event payload; raw prompts and outputs are not accepted."""

    name: str
    attributes: Mapping[str, str | int | bool]


class AIRoutingObserver(Protocol):
    """Adapter point for future OpenTelemetry metrics and spans."""

    def emit(self, event: AIRoutingMetricEvent) -> None: ...


class NullAIRoutingObserver:
    """Default no-op observer used until telemetry export is configured."""

    def emit(self, event: AIRoutingMetricEvent) -> None:
        del event
