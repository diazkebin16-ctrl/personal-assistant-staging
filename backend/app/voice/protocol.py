"""Bounded realtime wire protocol over one authenticated provider connection."""

import base64

from pydantic import TypeAdapter, ValidationError

from backend.app.voice.enums import (
    TranscriptKind,
    VoiceErrorCode,
    VoiceServerEventType,
    VoiceSessionState,
)
from backend.app.voice.provider import (
    RealtimeProviderConnection,
    RealtimeProviderFailure,
)
from backend.app.voice.schemas import (
    AudioFrameEvent,
    EndSessionEvent,
    InterruptEvent,
    PlaybackCompletedEvent,
    ProviderAudioEvent,
    ProviderTranscriptEvent,
    VoiceServerEvent,
    VoiceSessionAccess,
)
from backend.app.voice.service import VoiceSessionService

type VoiceClientEvent = AudioFrameEvent | InterruptEvent | EndSessionEvent | PlaybackCompletedEvent
_EVENT_ADAPTER: TypeAdapter[VoiceClientEvent] = TypeAdapter(VoiceClientEvent)


class MalformedVoiceEventError(ValueError):
    """Safe protocol failure without echoing the untrusted event."""


def parse_client_event(payload: str) -> VoiceClientEvent:
    if len(payload.encode()) > 12_000:
        raise MalformedVoiceEventError("Voice event exceeds the bounded wire size")
    try:
        return _EVENT_ADAPTER.validate_json(payload)
    except (ValidationError, ValueError):
        raise MalformedVoiceEventError("Voice event is invalid") from None


class VoiceProtocolCoordinator:
    """The only backend path from realtime audio into final assistant turns."""

    def __init__(
        self,
        service: VoiceSessionService,
        access: VoiceSessionAccess,
        provider: RealtimeProviderConnection,
    ) -> None:
        self.service = service
        self.access = access
        self.provider = provider
        self._last_audio_sequence: dict[str, int] = {}
        self._assistant_turn_id: str | None = None
        self.ended = False

    async def handle(self, event: VoiceClientEvent) -> tuple[VoiceServerEvent, ...]:
        if self.ended:
            raise MalformedVoiceEventError("Voice session is already ended")
        if isinstance(event, AudioFrameEvent):
            return await self._audio(event)
        if isinstance(event, InterruptEvent):
            if event.turn_id != self._assistant_turn_id:
                raise MalformedVoiceEventError("Cross-turn interruption rejected")
            await self.provider.interrupt(event.turn_id)
            state = await self.service.interrupt(self.access, event.turn_id)
            self._assistant_turn_id = None
            return (
                VoiceServerEvent(
                    type=VoiceServerEventType.TURN_INTERRUPTED,
                    turn_id=event.turn_id,
                ),
                VoiceServerEvent(type=VoiceServerEventType.SESSION_STATE, state=state),
            )
        if isinstance(event, PlaybackCompletedEvent):
            if event.turn_id != self._assistant_turn_id:
                raise MalformedVoiceEventError("Cross-turn playback completion rejected")
            state = await self.service.playback_completed(self.access, event.turn_id)
            self._assistant_turn_id = None
            return (VoiceServerEvent(type=VoiceServerEventType.SESSION_STATE, state=state),)
        if isinstance(event, EndSessionEvent):
            self.ended = True
            await self.provider.close()
            await self.service.disconnect(self.access, end=True)
            return (
                VoiceServerEvent(
                    type=VoiceServerEventType.SESSION_STATE,
                    state=VoiceSessionState.ENDED,
                ),
            )
        raise MalformedVoiceEventError("Unsupported voice event")

    async def _audio(self, event: AudioFrameEvent) -> tuple[VoiceServerEvent, ...]:
        previous = self._last_audio_sequence.get(event.turn_id, -1)
        if event.sequence != previous + 1:
            raise MalformedVoiceEventError("Audio event ordering is invalid")
        self._last_audio_sequence[event.turn_id] = event.sequence
        try:
            provider_events = await self.provider.send_audio(
                event.turn_id,
                event.sequence,
                event.audio_bytes(),
            )
        except (RealtimeProviderFailure, ValueError):
            raise MalformedVoiceEventError("Realtime provider event failed safely") from None

        results: list[VoiceServerEvent] = []
        final_seen = False
        for provider_event in provider_events:
            if not isinstance(provider_event, ProviderTranscriptEvent):
                raise MalformedVoiceEventError("Audio output before final authority is invalid")
            if provider_event.turn_id != event.turn_id:
                raise MalformedVoiceEventError("Cross-turn provider event rejected")
            results.append(self._transcript_event(provider_event))
            if provider_event.kind is TranscriptKind.PARTIAL:
                continue
            if final_seen:
                raise MalformedVoiceEventError("Duplicate final transcript event rejected")
            final_seen = True
            turn = await self.service.finalize_turn(
                self.access,
                provider_event.turn_id,
                provider_event.text,
                provider_event.confidence,
            )
            assistant = turn.response.assistant_message
            results.append(
                VoiceServerEvent(
                    type=VoiceServerEventType.ASSISTANT_TEXT,
                    turn_id=event.turn_id,
                    text=assistant.content,
                    outcome=assistant.outcome.value if assistant.outcome else None,
                    confirmation_request_id=assistant.confirmation_request_id,
                )
            )
            if turn.replayed:
                results.append(
                    VoiceServerEvent(
                        type=VoiceServerEventType.SESSION_STATE,
                        state=await self.service.state_for_connection(self.access),
                    )
                )
                continue
            try:
                audio_events = await self.provider.synthesize(event.turn_id, assistant.content)
            except RealtimeProviderFailure:
                raise MalformedVoiceEventError("Assistant audio failed safely") from None
            validated_audio = self._validated_audio_events(event.turn_id, audio_events)
            self._assistant_turn_id = event.turn_id
            results.append(
                VoiceServerEvent(
                    type=VoiceServerEventType.SESSION_STATE,
                    state=await self.service.state_for_connection(self.access),
                )
            )
            results.extend(self._audio_event(event.turn_id, item) for item in validated_audio)
        return tuple(results)

    @staticmethod
    def _validated_audio_events(
        turn_id: str,
        events: tuple[ProviderAudioEvent, ...],
    ) -> tuple[ProviderAudioEvent, ...]:
        if not events:
            raise MalformedVoiceEventError("Assistant audio is unavailable")
        final_seen = False
        for expected_sequence, event in enumerate(events):
            if event.turn_id != turn_id or event.sequence != expected_sequence or final_seen:
                raise MalformedVoiceEventError("Assistant audio ordering is invalid")
            final_seen = event.final
        if not final_seen:
            raise MalformedVoiceEventError("Assistant audio did not terminate")
        return events

    @staticmethod
    def _transcript_event(event: ProviderTranscriptEvent) -> VoiceServerEvent:
        return VoiceServerEvent(
            type=VoiceServerEventType.TRANSCRIPT,
            turn_id=event.turn_id,
            transcript_kind=event.kind,
            text=event.text,
            confidence=event.confidence,
        )

    @staticmethod
    def _audio_event(turn_id: str, event: ProviderAudioEvent) -> VoiceServerEvent:
        if event.turn_id != turn_id:
            raise MalformedVoiceEventError("Cross-turn assistant audio rejected")
        return VoiceServerEvent(
            type=VoiceServerEventType.ASSISTANT_AUDIO,
            turn_id=turn_id,
            audio_b64=base64.b64encode(event.audio).decode("ascii"),
            audio_sequence=event.sequence,
            audio_final=event.final,
        )

    async def fail(self, code: VoiceErrorCode) -> tuple[VoiceServerEvent, ...]:
        self.ended = True
        await self.provider.close()
        await self.service.disconnect(self.access, end=False)
        return (VoiceServerEvent(type=VoiceServerEventType.ERROR, error=code),)
