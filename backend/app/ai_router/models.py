"""Privacy-safe persistence for routing decisions and per-attempt usage telemetry."""

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

from backend.app.ai_router.enums import (
    FailureCategory,
    ModelClass,
    RoutingOutcome,
    UsageOutcome,
)
from backend.app.identity.models import Base, utc_now
from backend.app.security.classification import DataSensitivity


class RoutingDecisionRecord(Base):
    """Immutable routing evidence; raw prompts and model outputs are intentionally absent."""

    __tablename__ = "ai_routing_decisions"
    __table_args__ = (
        CheckConstraint("outcome IN ('SELECTED', 'DENIED')", name="ai_routing_outcome"),
        CheckConstraint(
            "model_class IS NULL OR model_class IN "
            "('FAST', 'STANDARD', 'ADVANCED', 'REALTIME', 'EMBEDDING', 'LOCAL')",
            name="ai_model_class",
        ),
        CheckConstraint(
            "effective_sensitivity IN ('PUBLIC', 'INTERNAL', 'PRIVATE', 'SENSITIVE', 'CRITICAL')",
            name="ai_routing_sensitivity",
        ),
        CheckConstraint(
            "(outcome = 'SELECTED' AND provider_key IS NOT NULL AND model_id IS NOT NULL "
            "AND model_class IS NOT NULL AND selected_quality IS NOT NULL) OR "
            "(outcome = 'DENIED' AND provider_key IS NULL AND model_id IS NULL "
            "AND model_class IS NULL AND selected_quality IS NULL)",
            name="ck_ai_routing_selection_shape",
        ),
        CheckConstraint(
            "selected_quality IS NULL OR selected_quality BETWEEN 1 AND 4", name="ck_ai_quality"
        ),
        CheckConstraint("estimated_input_tokens >= 0", name="ck_ai_input_tokens"),
        CheckConstraint("requested_output_tokens > 0", name="ck_ai_output_tokens"),
        CheckConstraint(
            "estimated_cost_microunits IS NULL OR estimated_cost_microunits >= 0",
            name="ck_ai_estimated_cost",
        ),
        CheckConstraint(
            "length(CAST(reason_codes AS TEXT)) <= 4096", name="ck_ai_reason_codes_size"
        ),
        CheckConstraint(
            "length(CAST(required_capabilities AS TEXT)) <= 4096",
            name="ck_ai_required_capabilities_size",
        ),
        CheckConstraint(
            "length(CAST(fallback_chain AS TEXT)) <= 8192", name="ck_ai_fallback_chain_size"
        ),
        Index("ix_ai_routing_user_created", "user_id", "created_at"),
        Index("ix_ai_routing_task_id", "task_id"),
        Index("ix_ai_routing_provider_model", "provider_key", "model_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    task_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    outcome: Mapped[RoutingOutcome] = mapped_column(
        SqlEnum(
            RoutingOutcome,
            name="ai_routing_outcome",
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
    )
    provider_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_class: Mapped[ModelClass | None] = mapped_column(
        SqlEnum(ModelClass, name="ai_model_class", native_enum=False, create_constraint=False),
        nullable=True,
    )
    selected_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    required_capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    effective_sensitivity: Mapped[DataSensitivity] = mapped_column(
        SqlEnum(
            DataSensitivity,
            name="ai_routing_sensitivity",
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
    )
    estimated_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    fallback_chain: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    estimated_cost_microunits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class AIUsageRecord(Base):
    """Append-oriented usage telemetry without raw prompt, response, or memory content."""

    __tablename__ = "ai_usage_records"
    __table_args__ = (
        CheckConstraint("attempt_number >= 1", name="ck_ai_usage_attempt"),
        CheckConstraint("input_tokens >= 0", name="ck_ai_usage_input_tokens"),
        CheckConstraint("output_tokens >= 0", name="ck_ai_usage_output_tokens"),
        CheckConstraint("cached_tokens >= 0", name="ck_ai_usage_cached_tokens"),
        CheckConstraint("latency_ms >= 0", name="ck_ai_usage_latency"),
        CheckConstraint("outcome IN ('SUCCESS', 'FAILURE')", name="ai_usage_outcome"),
        CheckConstraint(
            "failure_category IS NULL OR failure_category IN ("
            "'PROVIDER_UNAVAILABLE', 'RATE_LIMITED', 'TIMEOUT', 'AUTHENTICATION_ERROR', "
            "'INVALID_REQUEST', 'CONTEXT_LIMIT', 'CONTENT_POLICY', 'UNSUPPORTED_CAPABILITY', "
            "'MALFORMED_RESPONSE', 'INTERNAL_PROVIDER_ERROR', 'CANCELLED')",
            name="ai_failure_category",
        ),
        CheckConstraint(
            "(outcome = 'SUCCESS' AND failure_category IS NULL) OR "
            "(outcome = 'FAILURE' AND failure_category IS NOT NULL)",
            name="ck_ai_usage_outcome_shape",
        ),
        CheckConstraint("estimated_cost_microunits >= 0", name="ck_ai_usage_estimated_cost"),
        CheckConstraint(
            "actual_cost_microunits IS NULL OR actual_cost_microunits >= 0",
            name="ck_ai_usage_actual_cost",
        ),
        UniqueConstraint(
            "routing_decision_id", "attempt_number", name="uq_ai_usage_decision_attempt"
        ),
        Index("ix_ai_usage_user_timestamp", "user_id", "timestamp"),
        Index("ix_ai_usage_routing_decision", "routing_decision_id"),
        Index("ix_ai_usage_task_id", "task_id"),
        Index("ix_ai_usage_provider_model", "provider_key", "model_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    task_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    routing_decision_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("ai_routing_decisions.id", ondelete="RESTRICT"), nullable=False
    )
    provider_key: Mapped[str] = mapped_column(String(128), nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cached_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[UsageOutcome] = mapped_column(
        SqlEnum(
            UsageOutcome,
            name="ai_usage_outcome",
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
    )
    failure_category: Mapped[FailureCategory | None] = mapped_column(
        SqlEnum(
            FailureCategory,
            name="ai_failure_category",
            native_enum=False,
            create_constraint=False,
        ),
        nullable=True,
    )
    estimated_cost_microunits: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_cost_microunits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
