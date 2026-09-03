"""Privacy-safe, OpenTelemetry-compatible Text Assistant observation seam."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TextAssistantMetricEvent:
    name: str
    attributes: dict[str, str | int | bool]


class TextAssistantObserver(Protocol):
    def emit(self, event: TextAssistantMetricEvent) -> None: ...


class NullTextAssistantObserver:
    def emit(self, event: TextAssistantMetricEvent) -> None:
        del event
