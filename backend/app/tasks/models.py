"""Task, execution-attempt, and append-oriented lifecycle event persistence."""

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
from backend.app.tasks.enums import (
    TaskActorType,
    TaskAttemptStatus,
    TaskEventType,
    TaskPriority,
    TaskStatus,
)

_TASK_STATES = ", ".join(f"'{state.value}'" for state in TaskStatus)


class Task(Base):
    """Persisted unit of authorized or explicitly blocked future work."""

    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_tasks_user_idempotency"),
        CheckConstraint(f"status IN ({_TASK_STATES})", name="task_status"),
        CheckConstraint("priority IN ('LOW', 'NORMAL', 'HIGH', 'CRITICAL')", name="task_priority"),
        CheckConstraint("length(idempotency_key) BETWEEN 8 AND 128", name="ck_tasks_idem_length"),
        CheckConstraint("length(request_fingerprint) = 64", name="ck_tasks_fingerprint"),
        CheckConstraint("retry_count >= 0", name="ck_tasks_retry_nonnegative"),
        CheckConstraint("max_retries BETWEEN 0 AND 10", name="ck_tasks_max_retries"),
        CheckConstraint("retry_count <= max_retries + 1", name="ck_tasks_retry_bound"),
        CheckConstraint("version >= 1", name="ck_tasks_version_positive"),
        CheckConstraint(
            "parent_task_id IS NULL OR parent_task_id != id", name="ck_tasks_not_self_parent"
        ),
        CheckConstraint("length(CAST(scope AS TEXT)) <= 8192", name="ck_tasks_scope_size"),
        CheckConstraint("length(scope_digest) = 64", name="ck_tasks_scope_digest"),
        CheckConstraint("length(CAST(metadata AS TEXT)) <= 4096", name="ck_tasks_metadata_size"),
        CheckConstraint(
            "length(CAST(result_metadata AS TEXT)) <= 4096", name="ck_tasks_result_size"
        ),
        Index("ix_tasks_user_status_created", "user_id", "status", "created_at"),
        Index("ix_tasks_user_capability", "user_id", "capability_key"),
        Index("ix_tasks_next_retry", "next_retry_at"),
        Index("ix_tasks_authorization_decision", "authorization_decision_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("devices.id", ondelete="RESTRICT"), nullable=True
    )
    capability_key: Mapped[str] = mapped_column(
        String(128), ForeignKey("capabilities.key", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    scope_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        SqlEnum(TaskStatus, name="task_status", native_enum=False, create_constraint=False),
        nullable=False,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        SqlEnum(TaskPriority, name="task_priority", native_enum=False, create_constraint=False),
        default=TaskPriority.NORMAL,
        server_default=TaskPriority.NORMAL.value,
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    authorization_decision_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("authorization_decisions.id", ondelete="RESTRICT"), nullable=False
    )
    confirmation_request_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("confirmation_requests.id", ondelete="RESTRICT"), nullable=True
    )
    parent_task_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    metadata_payload: Mapped[dict[str, object]] = mapped_column("metadata", JSON, nullable=False)
    result_metadata: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)


class TaskAttempt(Base):
    """Preserved execution-attempt history; Phase 3 only models internal claims."""

    __tablename__ = "task_attempts"
    __table_args__ = (
        UniqueConstraint("task_id", "attempt_number", name="uq_task_attempt_number"),
        CheckConstraint("attempt_number >= 1", name="ck_attempt_number_positive"),
        CheckConstraint("status IN ('RUNNING', 'COMPLETED', 'FAILED')", name="task_attempt_status"),
        CheckConstraint("length(CAST(metadata AS TEXT)) <= 4096", name="ck_attempt_metadata_size"),
        Index("ix_task_attempts_task_started", "task_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[TaskAttemptStatus] = mapped_column(
        SqlEnum(
            TaskAttemptStatus,
            name="task_attempt_status",
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    safe_error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    worker_id: Mapped[str] = mapped_column(String(128), nullable=False)
    execution_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    metadata_payload: Mapped[dict[str, object]] = mapped_column("metadata", JSON, nullable=False)


class TaskEvent(Base):
    """Append-oriented domain history for Task lifecycle changes."""

    __tablename__ = "task_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('CREATED', 'STATE_CHANGED', 'CANCELLED', 'EXPIRED', "
            "'CLAIMED', 'COMPLETED', 'FAILED')",
            name="task_event_type",
        ),
        CheckConstraint(
            "actor_type IN ('USER', 'SYSTEM', 'AI', 'AUTOMATION', 'DEVICE', 'WORKER')",
            name="task_actor_type",
        ),
        CheckConstraint(
            "length(CAST(metadata AS TEXT)) <= 4096", name="ck_task_event_metadata_size"
        ),
        Index("ix_task_events_task_timestamp", "task_id", "timestamp"),
        Index("ix_task_events_user_timestamp", "user_id", "timestamp"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[TaskEventType] = mapped_column(
        SqlEnum(TaskEventType, name="task_event_type", native_enum=False, create_constraint=False),
        nullable=False,
    )
    from_state: Mapped[TaskStatus | None] = mapped_column(
        SqlEnum(TaskStatus, name="task_status", native_enum=False, create_constraint=False),
        nullable=True,
    )
    to_state: Mapped[TaskStatus] = mapped_column(
        SqlEnum(TaskStatus, name="task_status", native_enum=False, create_constraint=False),
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_type: Mapped[TaskActorType] = mapped_column(
        SqlEnum(TaskActorType, name="task_actor_type", native_enum=False, create_constraint=False),
        nullable=False,
    )
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_payload: Mapped[dict[str, object]] = mapped_column("metadata", JSON, nullable=False)
