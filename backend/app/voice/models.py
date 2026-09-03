"""Durable voice session/turn metadata; audio and transcripts are never duplicated here."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.identity.context import AuthenticationLevel
from backend.app.identity.models import Base, utc_now
from backend.app.security.classification import DataSensitivity
from backend.app.voice.enums import VoiceSessionState, VoiceTurnStatus

_SESSION_STATES = ",".join(f"'{item.value}'" for item in VoiceSessionState)
_TURN_STATES = ",".join(f"'{item.value}'" for item in VoiceTurnStatus)


class VoiceSession(Base):
    __tablename__ = "voice_sessions"
    __table_args__ = (
        CheckConstraint(f"state IN ({_SESSION_STATES})", name="ck_voice_session_state"),
        CheckConstraint("length(credential_hash) = 64", name="ck_voice_credential_hash"),
        CheckConstraint("reconnect_count BETWEEN 0 AND 3", name="ck_voice_reconnect_count"),
        CheckConstraint("version >= 1", name="ck_voice_session_version"),
        CheckConstraint("length(provider_key) BETWEEN 2 AND 128", name="ck_voice_provider_key"),
        CheckConstraint("length(model_id) BETWEEN 2 AND 128", name="ck_voice_model_id"),
        CheckConstraint("length(voice_profile) BETWEEN 2 AND 64", name="ck_voice_profile"),
        Index("ix_voice_sessions_user_created", "user_id", "created_at"),
        Index("ix_voice_sessions_device_state", "device_id", "state"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False
    )
    auth_session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("auth_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False
    )
    state: Mapped[VoiceSessionState] = mapped_column(
        SqlEnum(VoiceSessionState, native_enum=False), nullable=False
    )
    authentication_level: Mapped[AuthenticationLevel] = mapped_column(
        SqlEnum(AuthenticationLevel, native_enum=False), nullable=False
    )
    credential_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    credential_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    routing_decision_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("ai_routing_decisions.id", ondelete="RESTRICT"), nullable=False
    )
    provider_key: Mapped[str] = mapped_column(String(128), nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    voice_profile: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_sensitivity: Mapped[DataSensitivity] = mapped_column(
        SqlEnum(DataSensitivity, native_enum=False), nullable=False
    )
    reconnect_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    connection_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class VoiceTurn(Base):
    __tablename__ = "voice_turns"
    __table_args__ = (
        UniqueConstraint("session_id", "logical_turn_id", name="uq_voice_turn_session_logical"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_voice_turn_user_idempotency"),
        CheckConstraint(f"status IN ({_TURN_STATES})", name="ck_voice_turn_status"),
        CheckConstraint(
            "length(logical_turn_id) BETWEEN 8 AND 128", name="ck_voice_turn_logical_id"
        ),
        CheckConstraint(
            "length(idempotency_key) BETWEEN 8 AND 128", name="ck_voice_turn_idempotency"
        ),
        CheckConstraint("length(transcript_sha256) = 64", name="ck_voice_transcript_hash"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 10000)",
            name="ck_voice_turn_confidence",
        ),
        Index("ix_voice_turns_session_created", "session_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("voice_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False
    )
    logical_turn_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    transcript_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[VoiceTurnStatus] = mapped_column(
        SqlEnum(VoiceTurnStatus, native_enum=False), nullable=False
    )
    user_message_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("conversation_messages.id", ondelete="RESTRICT"), nullable=True
    )
    assistant_message_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("conversation_messages.id", ondelete="RESTRICT"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    interrupted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
