"""Privacy-safe Voice metrics boundary; content is structurally absent."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class VoiceMetricEvent:
    name: str
    attributes: dict[str, str | int | bool]


class VoiceObserver(Protocol):
    def emit(self, event: VoiceMetricEvent) -> None: ...


class NullVoiceObserver:
    def emit(self, event: VoiceMetricEvent) -> None:
        del event
