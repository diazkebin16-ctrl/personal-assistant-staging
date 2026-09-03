"""Append-oriented audit event persistence."""

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
    Uuid,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.identity.models import Base, utc_now
from backend.app.permissions.enums import ActorType, AuditEventType, AuditResult


class AuditEvent(Base):
    """Security evidence record; normal APIs expose no update or delete operation."""

    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('USER', 'SYSTEM', 'AI', 'AUTOMATION', 'DEVICE')",
            name="audit_actor_type",
        ),
        CheckConstraint(
            "event_type IN ("
            "'PERMISSION_GRANTED', 'PERMISSION_REVOKED', 'PERMISSION_EXPIRED_OBSERVED', "
            "'AUTHORIZATION_ALLOWED', 'AUTHORIZATION_DENIED', 'CONFIRMATION_REQUESTED', "
            "'CONFIRMATION_APPROVED', 'CONFIRMATION_REJECTED', "
            "'FINANCIAL_GUARD_TRIGGERED', 'TASK_CREATED', 'TASK_CANCELLED', "
            "'TASK_CLAIMED', 'MEMORY_CREATED', 'MEMORY_UPDATED', 'MEMORY_ARCHIVED', "
            "'MEMORY_DELETED', 'AI_ROUTING_DENIED', 'ORCHESTRATION_DENIED', "
            "'ORCHESTRATION_CONFIRMATION_REQUIRED', 'ORCHESTRATION_READY', "
            "'ORCHESTRATION_SECURITY_REJECTED', 'ORCHESTRATION_CANCELLED')",
            name="audit_event_type",
        ),
        CheckConstraint(
            "result IN ('RECORDED', 'ALLOWED', 'DENIED', 'REQUESTED', 'APPROVED', 'REJECTED')",
            name="audit_result",
        ),
        CheckConstraint(
            "risk_level IS NULL OR risk_level BETWEEN 0 AND 5",
            name="ck_audit_risk_level",
        ),
        CheckConstraint(
            "length(CAST(reason_codes AS TEXT)) <= 4096",
            name="ck_audit_reason_codes_size",
        ),
        CheckConstraint(
            "length(CAST(metadata AS TEXT)) <= 8192",
            name="ck_audit_metadata_size",
        ),
        Index("ix_audit_user_timestamp", "user_id", "timestamp"),
        Index("ix_audit_decision_id", "authorization_decision_id"),
        Index("ix_audit_permission_id", "permission_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True
    )
    session_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("auth_sessions.id", ondelete="SET NULL"), nullable=True
    )
    actor_type: Mapped[ActorType] = mapped_column(
        SqlEnum(
            ActorType,
            name="audit_actor_type",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
        ),
        nullable=False,
    )
    event_type: Mapped[AuditEventType] = mapped_column(
        SqlEnum(
            AuditEventType,
            name="audit_event_type",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
        ),
        nullable=False,
    )
    capability_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    risk_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    permission_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("permissions.id", ondelete="SET NULL"), nullable=True
    )
    authorization_decision_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("authorization_decisions.id", ondelete="SET NULL"), nullable=True
    )
    confirmation_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("confirmation_requests.id", ondelete="SET NULL"), nullable=True
    )
    result: Mapped[AuditResult] = mapped_column(
        SqlEnum(
            AuditResult,
            name="audit_result",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
        ),
        nullable=False,
    )
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    task_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    execution_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    metadata_payload: Mapped[dict[str, object]] = mapped_column("metadata", JSON, nullable=False)
