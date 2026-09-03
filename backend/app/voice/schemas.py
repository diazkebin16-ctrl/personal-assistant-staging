"""Strict public and provider-neutral Realtime Voice contracts."""

import base64
import binascii
import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from backend.app.core.time import as_utc
from backend.app.text_assistant.schemas import AssistantResponse
from backend.app.voice.enums import (
    TranscriptKind,
    VoiceClientEventType,
    VoiceErrorCode,
    VoiceServerEventType,
    VoiceSessionState,
)
from backend.app.voice.models import VoiceSession

VOICE_SAMPLE_RATE_HZ = 24_000
VOICE_CHANNELS = 1
VOICE_FRAME_DURATION_MS = 20
VOICE_FRAME_BYTES = 960
MAX_VOICE_FRAME_BYTES = 3_840
MAX_TRANSCRIPT_CHARACTERS = 50_000
MAX_RECONNECT_ATTEMPTS = 3

LogicalTurnId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]


class AudioFormat(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    encoding: Literal["PCM_S16LE"] = "PCM_S16LE"
    sample_rate_hz: Literal[24000] = 24000
    channels: Literal[1] = 1
    frame_duration_ms: Literal[20] = 20


class VoiceSessionCreateRequest(BaseModel):
    """User/device/model/sensitivity cannot be supplied by the client."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: UUID


class VoiceSessionCredentialResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: UUID
    credential: str = Field(min_length=32, max_length=256, repr=False)
    credential_expires_at: datetime


class VoiceSessionStateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: UUID
    state: VoiceSessionState


class VoiceSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    conversation_id: UUID
    state: VoiceSessionState
    audio_format: AudioFormat = Field(default_factory=AudioFormat)
    stream_path: str
    credential: str = Field(min_length=32, max_length=256, repr=False)
    credential_expires_at: datetime
    idle_timeout_seconds: int
    max_session_seconds: int
    max_reconnect_attempts: int = MAX_RECONNECT_ATTEMPTS
    started_at: datetime

    @classmethod
    def from_model(
        cls,
        session: VoiceSession,
        credential: str,
        *,
        idle_timeout_seconds: int,
        max_session_seconds: int,
    ) -> "VoiceSessionResponse":
        return cls(
            id=session.id,
            conversation_id=session.conversation_id,
            state=session.state,
            stream_path=f"/api/v1/voice/sessions/{session.id}/stream",
            credential=credential,
            credential_expires_at=as_utc(session.credential_expires_at),
            idle_timeout_seconds=idle_timeout_seconds,
            max_session_seconds=max_session_seconds,
            started_at=as_utc(session.started_at),
        )


class AudioFrameEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal[VoiceClientEventType.AUDIO_FRAME]
    turn_id: LogicalTurnId
    sequence: int = Field(ge=0, le=10_000_000)
    audio_b64: str = Field(min_length=4, max_length=MAX_VOICE_FRAME_BYTES * 2, repr=False)

    def audio_bytes(self) -> bytes:
        try:
            decoded = base64.b64decode(self.audio_b64, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("Malformed base64 audio frame") from None
        if not decoded or len(decoded) > MAX_VOICE_FRAME_BYTES or len(decoded) % 2:
            raise ValueError("Audio frame size is invalid")
        return decoded


class InterruptEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal[VoiceClientEventType.INTERRUPT]
    turn_id: LogicalTurnId


class EndSessionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal[VoiceClientEventType.END_SESSION]


class PlaybackCompletedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal[VoiceClientEventType.PLAYBACK_COMPLETED]
    turn_id: LogicalTurnId


class ProviderTranscriptEvent(BaseModel):
    """Provider output remains untrusted and is strictly validated."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    turn_id: LogicalTurnId
    kind: TranscriptKind
    text: str = Field(min_length=1, max_length=MAX_TRANSCRIPT_CHARACTERS, repr=False)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Transcript cannot be blank")
        return normalized


class ProviderAudioEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    turn_id: LogicalTurnId
    sequence: int = Field(ge=0, le=10_000_000)
    audio: bytes = Field(min_length=1, max_length=MAX_VOICE_FRAME_BYTES, repr=False)
    final: bool = False


class VoiceSessionAccess(BaseModel):
    """Server-created access context bound to one active socket generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: UUID
    connection_id: UUID
    user_id: UUID
    device_id: UUID
    conversation_id: UUID
    provider_key: str
    model_id: str
    voice_profile: str


class VoiceTurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    turn_id: LogicalTurnId
    response: AssistantResponse
    replayed: bool = False


class VoiceServerEvent(BaseModel):
    """Wire response with exactly one payload shape selected by type."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: VoiceServerEventType
    state: VoiceSessionState | None = None
    turn_id: str | None = None
    transcript_kind: TranscriptKind | None = None
    text: str | None = Field(default=None, repr=False)
    confidence: float | None = Field(default=None, ge=0, le=1)
    audio_b64: str | None = Field(default=None, repr=False)
    audio_sequence: int | None = Field(default=None, ge=0)
    audio_final: bool | None = None
    outcome: str | None = None
    confirmation_request_id: UUID | None = None
    error: VoiceErrorCode | None = None

    @field_validator("turn_id")
    @classmethod
    def validate_optional_turn_id(cls, value: str | None) -> str | None:
        if value is not None and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", value) is None:
            raise ValueError("Invalid turn identifier")
        return value
