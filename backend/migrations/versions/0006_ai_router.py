"""Create the Phase 5 AI Router routing and usage telemetry foundation.

Revision ID: 0006_ai_router
Revises: 0005_memory_core
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_ai_router"
down_revision: str | None = "0005_memory_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PHASE4_AUDIT_EVENTS = (
    "'PERMISSION_GRANTED', 'PERMISSION_REVOKED', 'PERMISSION_EXPIRED_OBSERVED', "
    "'AUTHORIZATION_ALLOWED', 'AUTHORIZATION_DENIED', 'CONFIRMATION_REQUESTED', "
    "'CONFIRMATION_APPROVED', 'CONFIRMATION_REJECTED', 'FINANCIAL_GUARD_TRIGGERED', "
    "'TASK_CREATED', 'TASK_CANCELLED', 'TASK_CLAIMED', 'MEMORY_CREATED', "
    "'MEMORY_UPDATED', 'MEMORY_ARCHIVED', 'MEMORY_DELETED'"
)
_PHASE5_AUDIT_EVENTS = _PHASE4_AUDIT_EVENTS + ", 'AI_ROUTING_DENIED'"

_RLS_STATEMENTS = (
    "ALTER TABLE public.ai_routing_decisions ENABLE ROW LEVEL SECURITY",
    "REVOKE ALL ON TABLE public.ai_routing_decisions FROM anon, authenticated",
    "GRANT SELECT ON TABLE public.ai_routing_decisions TO authenticated",
    """
    CREATE POLICY ai_routing_decisions_select_own
    ON public.ai_routing_decisions FOR SELECT TO authenticated
    USING (
        (SELECT auth.uid()) IS NOT NULL
        AND EXISTS (
            SELECT 1 FROM public.users owner
            WHERE owner.id = ai_routing_decisions.user_id
              AND owner.auth_user_id = (SELECT auth.uid())
        )
    )
    """,
    "ALTER TABLE public.ai_usage_records ENABLE ROW LEVEL SECURITY",
    "REVOKE ALL ON TABLE public.ai_usage_records FROM anon, authenticated",
    "GRANT SELECT ON TABLE public.ai_usage_records TO authenticated",
    """
    CREATE POLICY ai_usage_records_select_own
    ON public.ai_usage_records FOR SELECT TO authenticated
    USING (
        (SELECT auth.uid()) IS NOT NULL
        AND EXISTS (
            SELECT 1 FROM public.users owner
            WHERE owner.id = ai_usage_records.user_id
              AND owner.auth_user_id = (SELECT auth.uid())
        )
    )
    """,
)


def upgrade() -> None:
    """Add AI routing evidence and usage accounting without enabling any provider."""
    op.create_table(
        "ai_routing_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column(
            "outcome",
            sa.Enum(
                "SELECTED",
                "DENIED",
                name="ai_routing_outcome",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("provider_key", sa.String(length=128), nullable=True),
        sa.Column("model_id", sa.String(length=128), nullable=True),
        sa.Column(
            "model_class",
            sa.Enum(
                "FAST",
                "STANDARD",
                "ADVANCED",
                "REALTIME",
                "EMBEDDING",
                "LOCAL",
                name="ai_model_class",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=True,
        ),
        sa.Column("selected_quality", sa.Integer(), nullable=True),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("required_capabilities", sa.JSON(), nullable=False),
        sa.Column(
            "effective_sensitivity",
            sa.Enum(
                "PUBLIC",
                "INTERNAL",
                "PRIVATE",
                "SENSITIVE",
                "CRITICAL",
                name="ai_routing_sensitivity",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("estimated_input_tokens", sa.Integer(), nullable=False),
        sa.Column("requested_output_tokens", sa.Integer(), nullable=False),
        sa.Column("fallback_chain", sa.JSON(), nullable=False),
        sa.Column("estimated_cost_microunits", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("outcome IN ('SELECTED', 'DENIED')", name="ai_routing_outcome"),
        sa.CheckConstraint(
            "model_class IS NULL OR model_class IN "
            "('FAST', 'STANDARD', 'ADVANCED', 'REALTIME', 'EMBEDDING', 'LOCAL')",
            name="ai_model_class",
        ),
        sa.CheckConstraint(
            "effective_sensitivity IN ('PUBLIC', 'INTERNAL', 'PRIVATE', 'SENSITIVE', 'CRITICAL')",
            name="ai_routing_sensitivity",
        ),
        sa.CheckConstraint(
            "(outcome = 'SELECTED' AND provider_key IS NOT NULL AND model_id IS NOT NULL "
            "AND model_class IS NOT NULL AND selected_quality IS NOT NULL) OR "
            "(outcome = 'DENIED' AND provider_key IS NULL AND model_id IS NULL "
            "AND model_class IS NULL AND selected_quality IS NULL)",
            name="ck_ai_routing_selection_shape",
        ),
        sa.CheckConstraint(
            "selected_quality IS NULL OR selected_quality BETWEEN 1 AND 4",
            name="ck_ai_quality",
        ),
        sa.CheckConstraint("estimated_input_tokens >= 0", name="ck_ai_input_tokens"),
        sa.CheckConstraint("requested_output_tokens > 0", name="ck_ai_output_tokens"),
        sa.CheckConstraint(
            "estimated_cost_microunits IS NULL OR estimated_cost_microunits >= 0",
            name="ck_ai_estimated_cost",
        ),
        sa.CheckConstraint(
            "length(CAST(reason_codes AS TEXT)) <= 4096", name="ck_ai_reason_codes_size"
        ),
        sa.CheckConstraint(
            "length(CAST(required_capabilities AS TEXT)) <= 4096",
            name="ck_ai_required_capabilities_size",
        ),
        sa.CheckConstraint(
            "length(CAST(fallback_chain AS TEXT)) <= 8192",
            name="ck_ai_fallback_chain_size",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_routing_provider_model",
        "ai_routing_decisions",
        ["provider_key", "model_id"],
    )
    op.create_index("ix_ai_routing_task_id", "ai_routing_decisions", ["task_id"])
    op.create_index("ix_ai_routing_user_created", "ai_routing_decisions", ["user_id", "created_at"])

    op.create_table(
        "ai_usage_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("routing_decision_id", sa.Uuid(), nullable=False),
        sa.Column("provider_key", sa.String(length=128), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column(
            "outcome",
            sa.Enum(
                "SUCCESS",
                "FAILURE",
                name="ai_usage_outcome",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "failure_category",
            sa.Enum(
                "PROVIDER_UNAVAILABLE",
                "RATE_LIMITED",
                "TIMEOUT",
                "AUTHENTICATION_ERROR",
                "INVALID_REQUEST",
                "CONTEXT_LIMIT",
                "CONTENT_POLICY",
                "UNSUPPORTED_CAPABILITY",
                "MALFORMED_RESPONSE",
                "INTERNAL_PROVIDER_ERROR",
                "CANCELLED",
                name="ai_failure_category",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=True,
        ),
        sa.Column("estimated_cost_microunits", sa.Integer(), nullable=False),
        sa.Column("actual_cost_microunits", sa.Integer(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("attempt_number >= 1", name="ck_ai_usage_attempt"),
        sa.CheckConstraint("input_tokens >= 0", name="ck_ai_usage_input_tokens"),
        sa.CheckConstraint("output_tokens >= 0", name="ck_ai_usage_output_tokens"),
        sa.CheckConstraint("cached_tokens >= 0", name="ck_ai_usage_cached_tokens"),
        sa.CheckConstraint("latency_ms >= 0", name="ck_ai_usage_latency"),
        sa.CheckConstraint("outcome IN ('SUCCESS', 'FAILURE')", name="ai_usage_outcome"),
        sa.CheckConstraint(
            "failure_category IS NULL OR failure_category IN ("
            "'PROVIDER_UNAVAILABLE', 'RATE_LIMITED', 'TIMEOUT', 'AUTHENTICATION_ERROR', "
            "'INVALID_REQUEST', 'CONTEXT_LIMIT', 'CONTENT_POLICY', 'UNSUPPORTED_CAPABILITY', "
            "'MALFORMED_RESPONSE', 'INTERNAL_PROVIDER_ERROR', 'CANCELLED')",
            name="ai_failure_category",
        ),
        sa.CheckConstraint(
            "(outcome = 'SUCCESS' AND failure_category IS NULL) OR "
            "(outcome = 'FAILURE' AND failure_category IS NOT NULL)",
            name="ck_ai_usage_outcome_shape",
        ),
        sa.CheckConstraint("estimated_cost_microunits >= 0", name="ck_ai_usage_estimated_cost"),
        sa.CheckConstraint(
            "actual_cost_microunits IS NULL OR actual_cost_microunits >= 0",
            name="ck_ai_usage_actual_cost",
        ),
        sa.ForeignKeyConstraint(
            ["routing_decision_id"], ["ai_routing_decisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "routing_decision_id", "attempt_number", name="uq_ai_usage_decision_attempt"
        ),
    )
    op.create_index("ix_ai_usage_provider_model", "ai_usage_records", ["provider_key", "model_id"])
    op.create_index("ix_ai_usage_routing_decision", "ai_usage_records", ["routing_decision_id"])
    op.create_index("ix_ai_usage_task_id", "ai_usage_records", ["task_id"])
    op.create_index("ix_ai_usage_user_timestamp", "ai_usage_records", ["user_id", "timestamp"])

    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.drop_constraint("audit_event_type", type_="check")
        batch_op.create_check_constraint(
            "audit_event_type", f"event_type IN ({_PHASE5_AUDIT_EVENTS})"
        )

    if op.get_bind().dialect.name == "postgresql":
        for statement in _RLS_STATEMENTS:
            op.execute(statement)


def downgrade() -> None:
    """Remove Phase 5 objects while preserving all certified Phase 0-4 data."""
    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.drop_constraint("audit_event_type", type_="check")
        batch_op.create_check_constraint(
            "audit_event_type", f"event_type IN ({_PHASE4_AUDIT_EVENTS})"
        )

    op.drop_index("ix_ai_usage_user_timestamp", table_name="ai_usage_records")
    op.drop_index("ix_ai_usage_task_id", table_name="ai_usage_records")
    op.drop_index("ix_ai_usage_routing_decision", table_name="ai_usage_records")
    op.drop_index("ix_ai_usage_provider_model", table_name="ai_usage_records")
    op.drop_table("ai_usage_records")
    op.drop_index("ix_ai_routing_user_created", table_name="ai_routing_decisions")
    op.drop_index("ix_ai_routing_task_id", table_name="ai_routing_decisions")
    op.drop_index("ix_ai_routing_provider_model", table_name="ai_routing_decisions")
    op.drop_table("ai_routing_decisions")
