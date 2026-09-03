"""Create the Phase 3 Task Engine domain and restrictive RLS foundation.

Revision ID: 0004_task_engine
Revises: 0003_capability_actions
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_task_engine"
down_revision: str | None = "0003_capability_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TASK_STATES = (
    "'PENDING', 'QUEUED', 'WAITING_CONNECTION', 'WAITING_PERMISSION', "
    "'WAITING_CONFIRMATION', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', 'EXPIRED'"
)
_PHASE2_AUDIT_EVENTS = (
    "'PERMISSION_GRANTED', 'PERMISSION_REVOKED', 'PERMISSION_EXPIRED_OBSERVED', "
    "'AUTHORIZATION_ALLOWED', 'AUTHORIZATION_DENIED', 'CONFIRMATION_REQUESTED', "
    "'CONFIRMATION_APPROVED', 'CONFIRMATION_REJECTED', 'FINANCIAL_GUARD_TRIGGERED'"
)
_PHASE3_AUDIT_EVENTS = _PHASE2_AUDIT_EVENTS + ", 'TASK_CREATED', 'TASK_CANCELLED', 'TASK_CLAIMED'"

_RLS_STATEMENTS = (
    "ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY",
    "REVOKE ALL ON TABLE public.tasks FROM anon, authenticated",
    "GRANT SELECT ON TABLE public.tasks TO authenticated",
    """
    CREATE POLICY tasks_select_own
    ON public.tasks FOR SELECT TO authenticated
    USING (
        (SELECT auth.uid()) IS NOT NULL
        AND EXISTS (
            SELECT 1 FROM public.users owner
            WHERE owner.id = tasks.user_id
              AND owner.auth_user_id = (SELECT auth.uid())
        )
    )
    """,
    "ALTER TABLE public.task_attempts ENABLE ROW LEVEL SECURITY",
    "REVOKE ALL ON TABLE public.task_attempts FROM anon, authenticated",
    "GRANT SELECT ON TABLE public.task_attempts TO authenticated",
    """
    CREATE POLICY task_attempts_select_own
    ON public.task_attempts FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.tasks owned_task
            JOIN public.users owner ON owner.id = owned_task.user_id
            WHERE owned_task.id = task_attempts.task_id
              AND owner.auth_user_id = (SELECT auth.uid())
        )
    )
    """,
    "ALTER TABLE public.task_events ENABLE ROW LEVEL SECURITY",
    "REVOKE ALL ON TABLE public.task_events FROM anon, authenticated",
    "GRANT SELECT ON TABLE public.task_events TO authenticated",
    """
    CREATE POLICY task_events_select_own
    ON public.task_events FOR SELECT TO authenticated
    USING (
        (SELECT auth.uid()) IS NOT NULL
        AND EXISTS (
            SELECT 1 FROM public.users owner
            WHERE owner.id = task_events.user_id
              AND owner.auth_user_id = (SELECT auth.uid())
        )
    )
    """,
)


def upgrade() -> None:
    """Add Task Engine tables without modifying certified identity or authority data."""
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("capability_key", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("scope_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "QUEUED",
                "WAITING_CONNECTION",
                "WAITING_PERMISSION",
                "WAITING_CONFIRMATION",
                "RUNNING",
                "COMPLETED",
                "FAILED",
                "CANCELLED",
                "EXPIRED",
                name="task_status",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Enum(
                "LOW",
                "NORMAL",
                "HIGH",
                "CRITICAL",
                name="task_priority",
                native_enum=False,
                create_constraint=False,
            ),
            server_default="NORMAL",
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("authorization_decision_id", sa.Uuid(), nullable=False),
        sa.Column("confirmation_request_id", sa.Uuid(), nullable=True),
        sa.Column("parent_task_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("last_error_message", sa.String(length=500), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_retries", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("result_metadata", sa.JSON(), nullable=False),
        sa.CheckConstraint(f"status IN ({_TASK_STATES})", name="task_status"),
        sa.CheckConstraint(
            "priority IN ('LOW', 'NORMAL', 'HIGH', 'CRITICAL')", name="task_priority"
        ),
        sa.CheckConstraint(
            "length(idempotency_key) BETWEEN 8 AND 128", name="ck_tasks_idem_length"
        ),
        sa.CheckConstraint("length(request_fingerprint) = 64", name="ck_tasks_fingerprint"),
        sa.CheckConstraint("retry_count >= 0", name="ck_tasks_retry_nonnegative"),
        sa.CheckConstraint("max_retries BETWEEN 0 AND 10", name="ck_tasks_max_retries"),
        sa.CheckConstraint("retry_count <= max_retries + 1", name="ck_tasks_retry_bound"),
        sa.CheckConstraint("version >= 1", name="ck_tasks_version_positive"),
        sa.CheckConstraint(
            "parent_task_id IS NULL OR parent_task_id != id", name="ck_tasks_not_self_parent"
        ),
        sa.CheckConstraint("length(CAST(scope AS TEXT)) <= 8192", name="ck_tasks_scope_size"),
        sa.CheckConstraint("length(scope_digest) = 64", name="ck_tasks_scope_digest"),
        sa.CheckConstraint("length(CAST(metadata AS TEXT)) <= 4096", name="ck_tasks_metadata_size"),
        sa.CheckConstraint(
            "length(CAST(result_metadata AS TEXT)) <= 4096", name="ck_tasks_result_size"
        ),
        sa.ForeignKeyConstraint(
            ["authorization_decision_id"], ["authorization_decisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["capability_key"], ["capabilities.key"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["confirmation_request_id"], ["confirmation_requests.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_task_id"], ["tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_tasks_user_idempotency"),
    )
    op.create_index("ix_tasks_authorization_decision", "tasks", ["authorization_decision_id"])
    op.create_index("ix_tasks_next_retry", "tasks", ["next_retry_at"])
    op.create_index("ix_tasks_user_capability", "tasks", ["user_id", "capability_key"])
    op.create_index("ix_tasks_user_status_created", "tasks", ["user_id", "status", "created_at"])

    op.create_table(
        "task_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "RUNNING",
                "COMPLETED",
                "FAILED",
                name="task_attempt_status",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("safe_error_message", sa.String(length=500), nullable=True),
        sa.Column("worker_id", sa.String(length=128), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.CheckConstraint("attempt_number >= 1", name="ck_attempt_number_positive"),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED')", name="task_attempt_status"
        ),
        sa.CheckConstraint(
            "length(CAST(metadata AS TEXT)) <= 4096", name="ck_attempt_metadata_size"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "attempt_number", name="uq_task_attempt_number"),
    )
    op.create_index("ix_task_attempts_task_started", "task_attempts", ["task_id", "started_at"])

    op.create_table(
        "task_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "CREATED",
                "STATE_CHANGED",
                "CANCELLED",
                "EXPIRED",
                "CLAIMED",
                "COMPLETED",
                "FAILED",
                name="task_event_type",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "from_state",
            sa.Enum(
                *[state.strip(" '") for state in _TASK_STATES.split(",")],
                name="task_status",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "to_state",
            sa.Enum(
                *[state.strip(" '") for state in _TASK_STATES.split(",")],
                name="task_status",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column(
            "actor_type",
            sa.Enum(
                "USER",
                "SYSTEM",
                "AI",
                "AUTOMATION",
                "DEVICE",
                "WORKER",
                name="task_actor_type",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('CREATED', 'STATE_CHANGED', 'CANCELLED', 'EXPIRED', "
            "'CLAIMED', 'COMPLETED', 'FAILED')",
            name="task_event_type",
        ),
        sa.CheckConstraint(
            "actor_type IN ('USER', 'SYSTEM', 'AI', 'AUTOMATION', 'DEVICE', 'WORKER')",
            name="task_actor_type",
        ),
        sa.CheckConstraint(
            "length(CAST(metadata AS TEXT)) <= 4096", name="ck_task_event_metadata_size"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_events_task_timestamp", "task_events", ["task_id", "timestamp"])
    op.create_index("ix_task_events_user_timestamp", "task_events", ["user_id", "timestamp"])

    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.drop_constraint("audit_event_type", type_="check")
        batch_op.create_check_constraint(
            "audit_event_type", f"event_type IN ({_PHASE3_AUDIT_EVENTS})"
        )
        batch_op.create_foreign_key(
            "fk_audit_events_task_id_tasks", "tasks", ["task_id"], ["id"], ondelete="SET NULL"
        )

    if op.get_bind().dialect.name == "postgresql":
        for statement in _RLS_STATEMENTS:
            op.execute(statement)


def downgrade() -> None:
    """Remove only Phase 3 objects and restore the Phase 2 audit vocabulary."""
    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.drop_constraint("fk_audit_events_task_id_tasks", type_="foreignkey")
        batch_op.drop_constraint("audit_event_type", type_="check")
        batch_op.create_check_constraint(
            "audit_event_type", f"event_type IN ({_PHASE2_AUDIT_EVENTS})"
        )

    op.drop_index("ix_task_events_user_timestamp", table_name="task_events")
    op.drop_index("ix_task_events_task_timestamp", table_name="task_events")
    op.drop_table("task_events")
    op.drop_index("ix_task_attempts_task_started", table_name="task_attempts")
    op.drop_table("task_attempts")
    op.drop_index("ix_tasks_user_status_created", table_name="tasks")
    op.drop_index("ix_tasks_user_capability", table_name="tasks")
    op.drop_index("ix_tasks_next_retry", table_name="tasks")
    op.drop_index("ix_tasks_authorization_decision", table_name="tasks")
    op.drop_table("tasks")
