"""Owner-scoped memory, revision, and append-oriented event persistence."""

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
    Uuid,
    func,
    text,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.identity.models import Base, utc_now
from backend.app.memory.enums import (
    MemoryActorType,
    MemoryClass,
    MemoryEventType,
    MemorySourceType,
    MemoryStatus,
)
from backend.app.security.classification import DataSensitivity

_MEMORY_CLASSES = ", ".join(f"'{item.value}'" for item in MemoryClass)
_MEMORY_STATUSES = ", ".join(f"'{item.value}'" for item in MemoryStatus)
_MEMORY_SOURCES = ", ".join(f"'{item.value}'" for item in MemorySourceType)
_SENSITIVITY_CLASSES = ", ".join(f"'{item.value}'" for item in DataSensitivity)


class MemoryRecord(Base):
    """Canonical current memory state; authority fields are server-owned."""

    __tablename__ = "memory_records"
    __table_args__ = (
        CheckConstraint(f"memory_class IN ({_MEMORY_CLASSES})", name="memory_class"),
        CheckConstraint(f"status IN ({_MEMORY_STATUSES})", name="memory_status"),
        CheckConstraint(f"source_type IN ({_MEMORY_SOURCES})", name="memory_source_type"),
        CheckConstraint(f"sensitivity IN ({_SENSITIVITY_CLASSES})", name="memory_sensitivity"),
        CheckConstraint("length(content) BETWEEN 1 AND 16000", name="ck_memory_content_length"),
        CheckConstraint(
            "normalized_content IS NULL OR length(normalized_content) BETWEEN 1 AND 16000",
            name="ck_memory_normalized_length",
        ),
        CheckConstraint(
            "summary IS NULL OR length(summary) BETWEEN 1 AND 1000",
            name="ck_memory_summary_length",
        ),
        CheckConstraint(
            "subject IS NULL OR length(subject) BETWEEN 1 AND 200",
            name="ck_memory_subject_length",
        ),
        CheckConstraint(
            "source_reference IS NULL OR length(source_reference) BETWEEN 1 AND 255",
            name="ck_memory_source_reference_length",
        ),
        CheckConstraint("confidence BETWEEN 0 AND 100", name="ck_memory_confidence"),
        CheckConstraint("importance BETWEEN 0 AND 100", name="ck_memory_importance"),
        CheckConstraint("length(fingerprint) = 64", name="ck_memory_fingerprint"),
        CheckConstraint(
            "deduplication_key IS NULL OR length(deduplication_key) = 64",
            name="ck_memory_deduplication_key",
        ),
        CheckConstraint("version >= 1", name="ck_memory_version_positive"),
        CheckConstraint(
            "memory_class != 'TEMPORARY_CONTEXT' OR expires_at IS NOT NULL",
            name="ck_temporary_memory_expires",
        ),
        CheckConstraint(
            "expires_at IS NULL OR expires_at > created_at", name="ck_memory_expiry_after_creation"
        ),
        CheckConstraint(
            "status != 'ARCHIVED' OR archived_at IS NOT NULL", name="ck_archived_memory_timestamp"
        ),
        CheckConstraint(
            "status != 'EXPIRED' OR expires_at IS NOT NULL", name="ck_expired_memory_timestamp"
        ),
        CheckConstraint(
            "status != 'DELETED' OR deleted_at IS NOT NULL", name="ck_deleted_memory_timestamp"
        ),
        CheckConstraint("length(CAST(metadata AS TEXT)) <= 4096", name="ck_memory_metadata_size"),
        Index(
            "uq_memory_active_deduplication",
            "user_id",
            "memory_class",
            "deduplication_key",
            unique=True,
            sqlite_where=text("status = 'ACTIVE' AND deduplication_key IS NOT NULL"),
            postgresql_where=text("status = 'ACTIVE' AND deduplication_key IS NOT NULL"),
        ),
        Index("ix_memory_user_status_created", "user_id", "status", "created_at"),
        Index("ix_memory_user_class_updated", "user_id", "memory_class", "updated_at"),
        Index("ix_memory_user_subject", "user_id", "subject"),
        Index("ix_memory_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    source_device_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("devices.id", ondelete="RESTRICT"), nullable=True
    )
    memory_class: Mapped[MemoryClass] = mapped_column(
        SqlEnum(MemoryClass, name="memory_class", native_enum=False, create_constraint=False),
        nullable=False,
    )
    status: Mapped[MemoryStatus] = mapped_column(
        SqlEnum(MemoryStatus, name="memory_status", native_enum=False, create_constraint=False),
        default=MemoryStatus.ACTIVE,
        server_default=MemoryStatus.ACTIVE.value,
        nullable=False,
    )
    source_type: Mapped[MemorySourceType] = mapped_column(
        SqlEnum(
            MemorySourceType,
            name="memory_source_type",
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
    )
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    importance: Mapped[int] = mapped_column(Integer, nullable=False)
    sensitivity: Mapped[DataSensitivity] = mapped_column(
        SqlEnum(
            DataSensitivity,
            name="memory_sensitivity",
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    deduplication_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    metadata_payload: Mapped[dict[str, object]] = mapped_column("metadata", JSON, nullable=False)


class MemoryRevision(Base):
    """Immutable pre-update snapshot; privacy deletion scrubs its content in-place."""

    __tablename__ = "memory_revisions"
    __table_args__ = (
        Index("uq_memory_revision_number", "memory_id", "revision_number", unique=True),
        CheckConstraint(f"memory_class IN ({_MEMORY_CLASSES})", name="revision_memory_class"),
        CheckConstraint(f"source_type IN ({_MEMORY_SOURCES})", name="revision_memory_source_type"),
        CheckConstraint(
            f"sensitivity IN ({_SENSITIVITY_CLASSES})", name="revision_memory_sensitivity"
        ),
        CheckConstraint(
            "actor_type IN ('USER', 'SYSTEM', 'DEVICE')", name="revision_memory_actor_type"
        ),
        CheckConstraint("revision_number >= 1", name="ck_memory_revision_positive"),
        CheckConstraint("length(content) BETWEEN 1 AND 16000", name="ck_revision_content_length"),
        CheckConstraint(
            "normalized_content IS NULL OR length(normalized_content) BETWEEN 1 AND 16000",
            name="ck_revision_normalized_length",
        ),
        CheckConstraint("length(fingerprint) = 64", name="ck_revision_fingerprint"),
        CheckConstraint("length(CAST(metadata AS TEXT)) <= 4096", name="ck_revision_metadata_size"),
        Index("ix_memory_revisions_recorded", "memory_id", "recorded_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    memory_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("memory_records.id", ondelete="RESTRICT"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_class: Mapped[MemoryClass] = mapped_column(
        SqlEnum(MemoryClass, name="memory_class", native_enum=False, create_constraint=False),
        nullable=False,
    )
    source_type: Mapped[MemorySourceType] = mapped_column(
        SqlEnum(
            MemorySourceType,
            name="memory_source_type",
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
    )
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    importance: Mapped[int] = mapped_column(Integer, nullable=False)
    sensitivity: Mapped[DataSensitivity] = mapped_column(
        SqlEnum(
            DataSensitivity,
            name="memory_sensitivity",
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    actor_type: Mapped[MemoryActorType] = mapped_column(
        SqlEnum(
            MemoryActorType,
            name="memory_actor_type",
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
    )
    metadata_payload: Mapped[dict[str, object]] = mapped_column("metadata", JSON, nullable=False)


class MemoryEvent(Base):
    """Append-oriented domain chronology without raw memory content."""

    __tablename__ = "memory_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('CREATED', 'UPDATED', 'ARCHIVED', 'EXPIRED', 'DELETED', "
            "'DEDUPLICATED')",
            name="memory_event_type",
        ),
        CheckConstraint("actor_type IN ('USER', 'SYSTEM', 'DEVICE')", name="memory_actor_type"),
        CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_MEMORY_STATUSES})",
            name="memory_event_from_status",
        ),
        CheckConstraint(f"to_status IN ({_MEMORY_STATUSES})", name="memory_event_to_status"),
        CheckConstraint("length(reason_code) BETWEEN 1 AND 128", name="ck_memory_event_reason"),
        CheckConstraint(
            "length(CAST(metadata AS TEXT)) <= 4096", name="ck_memory_event_metadata_size"
        ),
        Index("ix_memory_events_memory_timestamp", "memory_id", "timestamp"),
        Index("ix_memory_events_user_timestamp", "user_id", "timestamp"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    memory_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("memory_records.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[MemoryEventType] = mapped_column(
        SqlEnum(
            MemoryEventType,
            name="memory_event_type",
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
    )
    from_status: Mapped[MemoryStatus | None] = mapped_column(
        SqlEnum(MemoryStatus, name="memory_status", native_enum=False, create_constraint=False),
        nullable=True,
    )
    to_status: Mapped[MemoryStatus] = mapped_column(
        SqlEnum(MemoryStatus, name="memory_status", native_enum=False, create_constraint=False),
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    actor_type: Mapped[MemoryActorType] = mapped_column(
        SqlEnum(
            MemoryActorType,
            name="memory_actor_type",
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
    )
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_payload: Mapped[dict[str, object]] = mapped_column("metadata", JSON, nullable=False)
