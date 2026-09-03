"""Durable, owner-scoped orchestration state and immutable coordination evidence."""

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
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.identity.models import Base, utc_now
from backend.app.orchestrator.enums import (
    IntentCategory,
    OrchestrationActor,
    OrchestrationState,
    OrchestrationStepType,
    SafeMode,
)

_STATES = ", ".join(f"'{item.value}'" for item in OrchestrationState)


class OrchestrationWorkflow(Base):
    """Minimal durable coordinator state; raw request/provider content is never stored."""

    __tablename__ = "orchestration_workflows"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_orchestration_user_idempotency"),
        CheckConstraint(f"state IN ({_STATES})", name="orchestration_state"),
        CheckConstraint(
            "intent_category IN ('INFORMATIONAL','MEMORY','ACTION','DESTRUCTIVE','UNSUPPORTED')",
            name="orchestration_intent_category",
        ),
        CheckConstraint(
            "safe_mode IN ('NORMAL','SAFE_MODE','MAINTENANCE')",
            name="orchestration_safe_mode",
        ),
        CheckConstraint(
            "length(request_fingerprint) = 64", name="ck_orchestration_request_fingerprint"
        ),
        CheckConstraint(
            "plan_fingerprint IS NULL OR length(plan_fingerprint) = 64",
            name="ck_orchestration_plan_fingerprint",
        ),
        CheckConstraint("version >= 1", name="ck_orchestration_version"),
        CheckConstraint(
            "length(CAST(intent_metadata AS TEXT)) <= 4096",
            name="ck_orchestration_intent_metadata_size",
        ),
        Index("ix_orchestration_user_state_created", "user_id", "state", "created_at"),
        Index("ix_orchestration_task", "task_id"),
        Index("ix_orchestration_routing", "routing_decision_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("devices.id", ondelete="RESTRICT"), nullable=True
    )
    intent_category: Mapped[IntentCategory] = mapped_column(
        SqlEnum(IntentCategory, native_enum=False), nullable=False
    )
    state: Mapped[OrchestrationState] = mapped_column(
        SqlEnum(OrchestrationState, native_enum=False), nullable=False
    )
    safe_mode: Mapped[SafeMode] = mapped_column(
        SqlEnum(SafeMode, native_enum=False), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    task_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=True
    )
    routing_decision_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_routing_decisions.id", ondelete="RESTRICT"), nullable=True
    )
    authorization_decision_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("authorization_decisions.id", ondelete="RESTRICT"), nullable=True
    )
    confirmation_request_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("confirmation_requests.id", ondelete="RESTRICT"), nullable=True
    )
    failure_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    intent_metadata: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ValidatedPlan(Base):
    """One immutable, schema-validated plan per workflow."""

    __tablename__ = "orchestration_plans"
    __table_args__ = (
        UniqueConstraint("workflow_id", name="uq_orchestration_plan_workflow"),
        CheckConstraint("length(fingerprint) = 64", name="ck_orchestration_plan_hash"),
        CheckConstraint(
            "length(CAST(plan_payload AS TEXT)) <= 16384", name="ck_orchestration_plan_size"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("orchestration_workflows.id", ondelete="RESTRICT"), nullable=False
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class OrchestrationStep(Base):
    """Append-oriented transition evidence, distinct from TaskEvent and AuditEvent."""

    __tablename__ = "orchestration_steps"
    __table_args__ = (
        CheckConstraint(
            "length(CAST(metadata AS TEXT)) <= 4096", name="ck_orchestration_step_metadata_size"
        ),
        Index("ix_orchestration_steps_workflow_created", "workflow_id", "created_at"),
        Index("ix_orchestration_steps_user_created", "user_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("orchestration_workflows.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    step_type: Mapped[OrchestrationStepType] = mapped_column(
        SqlEnum(OrchestrationStepType, native_enum=False), nullable=False
    )
    from_state: Mapped[OrchestrationState | None] = mapped_column(
        SqlEnum(OrchestrationState, native_enum=False), nullable=True
    )
    to_state: Mapped[OrchestrationState] = mapped_column(
        SqlEnum(OrchestrationState, native_enum=False), nullable=False
    )
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_type: Mapped[OrchestrationActor] = mapped_column(
        SqlEnum(OrchestrationActor, native_enum=False), nullable=False
    )
    metadata_payload: Mapped[dict[str, object]] = mapped_column("metadata", JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class AuthorizedActionEnvelopeRecord(Base):
    """Immutable future-executor handoff evidence; this table grants no execution authority."""

    __tablename__ = "authorized_action_envelopes"
    __table_args__ = (
        UniqueConstraint("workflow_id", name="uq_authorized_envelope_workflow"),
        CheckConstraint("length(plan_fingerprint) = 64", name="ck_envelope_plan_hash"),
        CheckConstraint("length(scope_digest) = 64", name="ck_envelope_scope_digest"),
        CheckConstraint(
            "length(CAST(arguments AS TEXT)) <= 8192", name="ck_envelope_arguments_size"
        ),
        CheckConstraint("risk_level BETWEEN 0 AND 5", name="ck_envelope_risk"),
        CheckConstraint("safe_mode = 'NORMAL'", name="ck_envelope_normal_mode"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("orchestration_workflows.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("devices.id", ondelete="RESTRICT"), nullable=True
    )
    task_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False
    )
    capability_key: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    arguments: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    scope_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    permission_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("permissions.id", ondelete="RESTRICT"), nullable=False
    )
    authorization_decision_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("authorization_decisions.id", ondelete="RESTRICT"), nullable=False
    )
    confirmation_request_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("confirmation_requests.id", ondelete="RESTRICT"), nullable=True
    )
    risk_level: Mapped[int] = mapped_column(Integer, nullable=False)
    safe_mode: Mapped[SafeMode] = mapped_column(
        SqlEnum(SafeMode, native_enum=False), nullable=False
    )
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
