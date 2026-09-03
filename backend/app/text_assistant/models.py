"""Durable owner-scoped conversations; conversation history is not Memory."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.identity.models import Base, utc_now
from backend.app.security.classification import DataSensitivity
from backend.app.text_assistant.enums import AssistantOutcome, MessageRole, MessageStatus

_OUTCOMES = ",".join(f"'{item.value}'" for item in AssistantOutcome)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "title IS NULL OR length(title) BETWEEN 1 AND 200", name="ck_conversation_title"
        ),
        CheckConstraint("version >= 1", name="ck_conversation_version"),
        CheckConstraint("next_sequence >= 1", name="ck_conversation_next_sequence"),
        Index("ix_conversations_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("devices.id", ondelete="RESTRICT"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    next_sequence: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence", name="uq_message_conversation_sequence"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_message_user_idempotency"),
        CheckConstraint("sequence >= 1", name="ck_message_sequence"),
        CheckConstraint("length(content) BETWEEN 1 AND 100000", name="ck_message_content"),
        CheckConstraint("role IN ('USER','ASSISTANT')", name="ck_message_role"),
        CheckConstraint("status IN ('COMPLETED','FAILED')", name="ck_message_status"),
        CheckConstraint(
            "sensitivity IN ('PUBLIC','INTERNAL','PRIVATE','SENSITIVE','CRITICAL')",
            name="ck_message_sensitivity",
        ),
        CheckConstraint(f"outcome IS NULL OR outcome IN ({_OUTCOMES})", name="ck_message_outcome"),
        CheckConstraint(
            "(role = 'USER' AND idempotency_key IS NOT NULL AND request_fingerprint IS NOT NULL "
            "AND outcome IS NULL AND reply_to_message_id IS NULL AND status = 'COMPLETED') OR "
            "(role = 'ASSISTANT' AND idempotency_key IS NULL AND request_fingerprint IS NULL "
            "AND outcome IS NOT NULL AND reply_to_message_id IS NOT NULL)",
            name="ck_message_role_contract",
        ),
        CheckConstraint(
            "request_fingerprint IS NULL OR length(request_fingerprint) = 64",
            name="ck_message_request_fingerprint",
        ),
        CheckConstraint(
            "length(CAST(research_citations AS TEXT)) <= 65536",
            name="ck_message_research_citations_size",
        ),
        Index("ix_messages_conversation_sequence", "conversation_id", "sequence"),
        Index("ix_messages_user_created", "user_id", "created_at"),
        Index("ix_messages_reply_to", "reply_to_message_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(
        SqlEnum(MessageRole, native_enum=False), nullable=False
    )
    status: Mapped[MessageStatus] = mapped_column(
        SqlEnum(MessageStatus, native_enum=False), nullable=False
    )
    outcome: Mapped[AssistantOutcome | None] = mapped_column(
        SqlEnum(AssistantOutcome, native_enum=False), nullable=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sensitivity: Mapped[DataSensitivity] = mapped_column(
        SqlEnum(DataSensitivity, native_enum=False), nullable=False
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reply_to_message_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("conversation_messages.id", ondelete="RESTRICT"), nullable=True
    )
    routing_decision_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_routing_decisions.id", ondelete="RESTRICT"), nullable=True
    )
    orchestration_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("orchestration_workflows.id", ondelete="RESTRICT"), nullable=True
    )
    confirmation_request_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("confirmation_requests.id", ondelete="RESTRICT"), nullable=True
    )
    memory_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("memory_records.id", ondelete="RESTRICT"), nullable=True
    )
    reason_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    research_citations: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, default=list, server_default="[]", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
