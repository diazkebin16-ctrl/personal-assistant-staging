"""Provider-neutral realtime transport boundary and deterministic fake adapter."""

import asyncio
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from backend.app.voice.enums import VoiceErrorCode
from backend.app.voice.schemas import ProviderAudioEvent, ProviderTranscriptEvent

RealtimeProviderEvent = ProviderTranscriptEvent | ProviderAudioEvent


class RealtimeProviderFailure(Exception):
    def __init__(self, code: VoiceErrorCode) -> None:
        super().__init__(f"Realtime provider failed: {code.value}")
        self.code = code


@runtime_checkable
class RealtimeProviderConnection(Protocol):
    async def send_audio(
        self, turn_id: str, sequence: int, audio: bytes
    ) -> tuple[RealtimeProviderEvent, ...]: ...

    async def synthesize(self, turn_id: str, text: str) -> tuple[ProviderAudioEvent, ...]: ...

    async def interrupt(self, turn_id: str) -> None: ...

    async def close(self) -> None: ...


@runtime_checkable
class RealtimeProvider(Protocol):
    @property
    def key(self) -> str: ...

    async def connect(self, model_id: str, voice_profile: str) -> RealtimeProviderConnection: ...


class RealtimeProviderRegistry:
    """Server-owned immutable registry; request data cannot add an adapter."""

    def __init__(self, providers: Iterable[RealtimeProvider] = ()) -> None:
        items: dict[str, RealtimeProvider] = {}
        for provider in providers:
            if provider.key in items:
                raise ValueError(f"Duplicate realtime provider adapter: {provider.key}")
            items[provider.key] = provider
        self._providers = items

    def get(self, key: str) -> RealtimeProvider:
        try:
            return self._providers[key]
        except KeyError:
            raise RealtimeProviderFailure(VoiceErrorCode.PROVIDER_UNAVAILABLE) from None


class FakeRealtimeConnection:
    """No-network scripted connection for state, interruption, and E2E tests."""

    def __init__(
        self,
        input_events: Iterable[tuple[RealtimeProviderEvent, ...]],
        audio_responses: Iterable[tuple[ProviderAudioEvent, ...]],
    ) -> None:
        self._input_events = tuple(input_events)
        self._audio_responses = tuple(audio_responses)
        self._input_index = 0
        self._output_index = 0
        self._lock = asyncio.Lock()
        self.closed = False
        self.interrupted_turns: list[str] = []
        self.received_frames: list[tuple[str, int, int]] = []

    async def send_audio(
        self, turn_id: str, sequence: int, audio: bytes
    ) -> tuple[RealtimeProviderEvent, ...]:
        async with self._lock:
            if self.closed:
                raise RealtimeProviderFailure(VoiceErrorCode.PROVIDER_UNAVAILABLE)
            self.received_frames.append((turn_id, sequence, len(audio)))
            if self._input_index >= len(self._input_events):
                return ()
            result = self._input_events[self._input_index]
            self._input_index += 1
            return result

    async def synthesize(self, turn_id: str, text: str) -> tuple[ProviderAudioEvent, ...]:
        del text
        async with self._lock:
            if self.closed:
                raise RealtimeProviderFailure(VoiceErrorCode.PROVIDER_UNAVAILABLE)
            if self._output_index >= len(self._audio_responses):
                return ()
            result = self._audio_responses[self._output_index]
            self._output_index += 1
            if any(item.turn_id != turn_id for item in result):
                raise RealtimeProviderFailure(VoiceErrorCode.MALFORMED_EVENT)
            return result

    async def interrupt(self, turn_id: str) -> None:
        self.interrupted_turns.append(turn_id)

    async def close(self) -> None:
        self.closed = True


class FakeRealtimeProvider:
    """Explicitly injected fake. It is absent from production composition."""

    def __init__(
        self,
        key: str,
        input_events: Iterable[tuple[RealtimeProviderEvent, ...]],
        audio_responses: Iterable[tuple[ProviderAudioEvent, ...]],
    ) -> None:
        self._key = key
        self._input_events = tuple(input_events)
        self._audio_responses = tuple(audio_responses)
        self.connections: list[FakeRealtimeConnection] = []

    @property
    def key(self) -> str:
        return self._key

    async def connect(self, model_id: str, voice_profile: str) -> FakeRealtimeConnection:
        del model_id, voice_profile
        connection = FakeRealtimeConnection(self._input_events, self._audio_responses)
        self.connections.append(connection)
        return connection
