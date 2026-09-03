"""Add durable Phase 6 Orchestrator coordination and immutable handoff evidence.

Revision ID: 0007_orchestrator
Revises: 0006_ai_router
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_orchestrator"
down_revision: str | None = "0006_ai_router"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PHASE5_AUDIT_EVENTS = (
    "'PERMISSION_GRANTED', 'PERMISSION_REVOKED', 'PERMISSION_EXPIRED_OBSERVED', "
    "'AUTHORIZATION_ALLOWED', 'AUTHORIZATION_DENIED', 'CONFIRMATION_REQUESTED', "
    "'CONFIRMATION_APPROVED', 'CONFIRMATION_REJECTED', 'FINANCIAL_GUARD_TRIGGERED', "
    "'TASK_CREATED', 'TASK_CANCELLED', 'TASK_CLAIMED', 'MEMORY_CREATED', "
    "'MEMORY_UPDATED', 'MEMORY_ARCHIVED', 'MEMORY_DELETED', 'AI_ROUTING_DENIED'"
)
_PHASE6_AUDIT_EVENTS = _PHASE5_AUDIT_EVENTS + (
    ", 'ORCHESTRATION_DENIED', 'ORCHESTRATION_CONFIRMATION_REQUIRED', "
    "'ORCHESTRATION_READY', 'ORCHESTRATION_SECURITY_REJECTED', "
    "'ORCHESTRATION_CANCELLED'"
)

_STATES = (
    "'RECEIVED', 'CONTEXT_PREPARED', 'ROUTED', 'PROPOSAL_GENERATED', "
    "'PLAN_VALIDATED', 'WAITING_PERMISSION', 'WAITING_CONFIRMATION', "
    "'READY_FOR_EXECUTION', 'COMPLETED_NO_ACTION', 'DENIED', 'FAILED', "
    "'CANCELLED', 'EXPIRED'"
)


def upgrade() -> None:
    op.create_table(
        "orchestration_workflows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column(
            "intent_category",
            sa.Enum(
                "INFORMATIONAL",
                "MEMORY",
                "ACTION",
                "DESTRUCTIVE",
                "UNSUPPORTED",
                name="intentcategory",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.Enum(
                "RECEIVED",
                "CONTEXT_PREPARED",
                "ROUTED",
                "PROPOSAL_GENERATED",
                "PLAN_VALIDATED",
                "WAITING_PERMISSION",
                "WAITING_CONFIRMATION",
                "READY_FOR_EXECUTION",
                "COMPLETED_NO_ACTION",
                "DENIED",
                "FAILED",
                "CANCELLED",
                "EXPIRED",
                name="orchestrationstate",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "safe_mode",
            sa.Enum(
                "NORMAL",
                "SAFE_MODE",
                "MAINTENANCE",
                name="safemode",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("plan_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("routing_decision_id", sa.Uuid(), nullable=True),
        sa.Column("authorization_decision_id", sa.Uuid(), nullable=True),
        sa.Column("confirmation_request_id", sa.Uuid(), nullable=True),
        sa.Column("failure_reason", sa.String(length=128), nullable=True),
        sa.Column("intent_metadata", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
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
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"state IN ({_STATES})", name="orchestration_state"),
        sa.CheckConstraint(
            "intent_category IN ('INFORMATIONAL','MEMORY','ACTION','DESTRUCTIVE','UNSUPPORTED')",
            name="orchestration_intent_category",
        ),
        sa.CheckConstraint(
            "safe_mode IN ('NORMAL','SAFE_MODE','MAINTENANCE')", name="orchestration_safe_mode"
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64", name="ck_orchestration_request_fingerprint"
        ),
        sa.CheckConstraint(
            "plan_fingerprint IS NULL OR length(plan_fingerprint) = 64",
            name="ck_orchestration_plan_fingerprint",
        ),
        sa.CheckConstraint("version >= 1", name="ck_orchestration_version"),
        sa.CheckConstraint(
            "length(CAST(intent_metadata AS TEXT)) <= 4096",
            name="ck_orchestration_intent_metadata_size",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["routing_decision_id"], ["ai_routing_decisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["authorization_decision_id"], ["authorization_decisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["confirmation_request_id"], ["confirmation_requests.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_orchestration_user_idempotency"),
    )
    op.create_index(
        "ix_orchestration_user_state_created",
        "orchestration_workflows",
        ["user_id", "state", "created_at"],
    )
    op.create_index("ix_orchestration_task", "orchestration_workflows", ["task_id"])
    op.create_index("ix_orchestration_routing", "orchestration_workflows", ["routing_decision_id"])

    op.create_table(
        "orchestration_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("plan_payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("length(fingerprint) = 64", name="ck_orchestration_plan_hash"),
        sa.CheckConstraint(
            "length(CAST(plan_payload AS TEXT)) <= 16384", name="ck_orchestration_plan_size"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id"], ["orchestration_workflows.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id", name="uq_orchestration_plan_workflow"),
    )
    op.create_table(
        "orchestration_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "step_type",
            sa.Enum(
                "RECEIVED",
                "CONTEXT_SELECTED",
                "AI_ROUTED",
                "PROPOSAL_VALIDATED",
                "TASK_LINKED",
                "AUTHORITY_BLOCKED",
                "EXECUTION_ENVELOPE_CREATED",
                "CANCELLED",
                "EXPIRED",
                "FAILED",
                name="orchestrationsteptype",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "from_state",
            sa.Enum(
                "RECEIVED",
                "CONTEXT_PREPARED",
                "ROUTED",
                "PROPOSAL_GENERATED",
                "PLAN_VALIDATED",
                "WAITING_PERMISSION",
                "WAITING_CONFIRMATION",
                "READY_FOR_EXECUTION",
                "COMPLETED_NO_ACTION",
                "DENIED",
                "FAILED",
                "CANCELLED",
                "EXPIRED",
                name="orchestrationstate",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "to_state",
            sa.Enum(
                "RECEIVED",
                "CONTEXT_PREPARED",
                "ROUTED",
                "PROPOSAL_GENERATED",
                "PLAN_VALIDATED",
                "WAITING_PERMISSION",
                "WAITING_CONFIRMATION",
                "READY_FOR_EXECUTION",
                "COMPLETED_NO_ACTION",
                "DENIED",
                "FAILED",
                "CANCELLED",
                "EXPIRED",
                name="orchestrationstate",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column(
            "actor_type",
            sa.Enum(
                "USER",
                "SYSTEM",
                name="orchestrationactor",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(CAST(metadata AS TEXT)) <= 4096", name="ck_orchestration_step_metadata_size"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id"], ["orchestration_workflows.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_orchestration_steps_workflow_created",
        "orchestration_steps",
        ["workflow_id", "created_at"],
    )
    op.create_index(
        "ix_orchestration_steps_user_created", "orchestration_steps", ["user_id", "created_at"]
    )
    op.create_table(
        "authorized_action_envelopes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("capability_key", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("scope_digest", sa.String(length=64), nullable=False),
        sa.Column("plan_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.Column("authorization_decision_id", sa.Uuid(), nullable=False),
        sa.Column("confirmation_request_id", sa.Uuid(), nullable=True),
        sa.Column("risk_level", sa.Integer(), nullable=False),
        sa.Column(
            "safe_mode",
            sa.Enum(
                "NORMAL",
                "SAFE_MODE",
                "MAINTENANCE",
                name="safemode",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("length(plan_fingerprint) = 64", name="ck_envelope_plan_hash"),
        sa.CheckConstraint("length(scope_digest) = 64", name="ck_envelope_scope_digest"),
        sa.CheckConstraint("risk_level BETWEEN 0 AND 5", name="ck_envelope_risk"),
        sa.CheckConstraint("safe_mode = 'NORMAL'", name="ck_envelope_normal_mode"),
        sa.CheckConstraint(
            "length(CAST(arguments AS TEXT)) <= 8192", name="ck_envelope_arguments_size"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id"], ["orchestration_workflows.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["authorization_decision_id"], ["authorization_decisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["confirmation_request_id"], ["confirmation_requests.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id", name="uq_authorized_envelope_workflow"),
    )

    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.drop_constraint("audit_event_type", type_="check")
        batch_op.alter_column(
            "event_type",
            type_=sa.Enum(
                "PERMISSION_GRANTED",
                "PERMISSION_REVOKED",
                "PERMISSION_EXPIRED_OBSERVED",
                "AUTHORIZATION_ALLOWED",
                "AUTHORIZATION_DENIED",
                "CONFIRMATION_REQUESTED",
                "CONFIRMATION_APPROVED",
                "CONFIRMATION_REJECTED",
                "FINANCIAL_GUARD_TRIGGERED",
                "TASK_CREATED",
                "TASK_CANCELLED",
                "TASK_CLAIMED",
                "MEMORY_CREATED",
                "MEMORY_UPDATED",
                "MEMORY_ARCHIVED",
                "MEMORY_DELETED",
                "AI_ROUTING_DENIED",
                "ORCHESTRATION_DENIED",
                "ORCHESTRATION_CONFIRMATION_REQUIRED",
                "ORCHESTRATION_READY",
                "ORCHESTRATION_SECURITY_REJECTED",
                "ORCHESTRATION_CANCELLED",
                name="audit_event_type",
                native_enum=False,
                create_constraint=False,
            ),
        )
        batch_op.create_check_constraint(
            "audit_event_type", f"event_type IN ({_PHASE6_AUDIT_EVENTS})"
        )

    if op.get_bind().dialect.name == "postgresql":
        for table in (
            "orchestration_workflows",
            "orchestration_plans",
            "orchestration_steps",
            "authorized_action_envelopes",
        ):
            op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"REVOKE ALL ON TABLE public.{table} FROM anon, authenticated")
            op.execute(f"GRANT SELECT ON TABLE public.{table} TO authenticated")
        op.execute("""
            CREATE POLICY orchestration_workflows_select_own ON public.orchestration_workflows
            FOR SELECT TO authenticated USING (EXISTS (
              SELECT 1 FROM public.users owner WHERE owner.id = orchestration_workflows.user_id
              AND owner.auth_user_id = (SELECT auth.uid())))
        """)
        policy_statements = (
            """CREATE POLICY orchestration_plans_select_own ON public.orchestration_plans
            FOR SELECT TO authenticated USING (EXISTS (
              SELECT 1 FROM public.orchestration_workflows workflow
              JOIN public.users owner ON owner.id = workflow.user_id
              WHERE workflow.id = orchestration_plans.workflow_id
              AND owner.auth_user_id = (SELECT auth.uid())))""",
            """CREATE POLICY orchestration_steps_select_own ON public.orchestration_steps
            FOR SELECT TO authenticated USING (EXISTS (
              SELECT 1 FROM public.orchestration_workflows workflow
              JOIN public.users owner ON owner.id = workflow.user_id
              WHERE workflow.id = orchestration_steps.workflow_id
              AND owner.auth_user_id = (SELECT auth.uid())))""",
            """CREATE POLICY authorized_action_envelopes_select_own
            ON public.authorized_action_envelopes FOR SELECT TO authenticated USING (EXISTS (
              SELECT 1 FROM public.orchestration_workflows workflow
              JOIN public.users owner ON owner.id = workflow.user_id
              WHERE workflow.id = authorized_action_envelopes.workflow_id
              AND owner.auth_user_id = (SELECT auth.uid())))""",
        )
        for statement in policy_statements:
            op.execute(statement)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in (
            "authorized_action_envelopes",
            "orchestration_steps",
            "orchestration_workflows",
        ):
            op.execute(f"DROP POLICY IF EXISTS {table}_select_own ON public.{table}")
    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.drop_constraint("audit_event_type", type_="check")
        batch_op.alter_column(
            "event_type",
            type_=sa.Enum(
                "PERMISSION_GRANTED",
                "PERMISSION_REVOKED",
                "PERMISSION_EXPIRED_OBSERVED",
                "AUTHORIZATION_ALLOWED",
                "AUTHORIZATION_DENIED",
                "CONFIRMATION_REQUESTED",
                "CONFIRMATION_APPROVED",
                "CONFIRMATION_REJECTED",
                "FINANCIAL_GUARD_TRIGGERED",
                "TASK_CREATED",
                "TASK_CANCELLED",
                "TASK_CLAIMED",
                "MEMORY_CREATED",
                "MEMORY_UPDATED",
                "MEMORY_ARCHIVED",
                "MEMORY_DELETED",
                "AI_ROUTING_DENIED",
                name="audit_event_type",
                native_enum=False,
                create_constraint=False,
            ),
        )
        batch_op.create_check_constraint(
            "audit_event_type", f"event_type IN ({_PHASE5_AUDIT_EVENTS})"
        )
    op.drop_table("authorized_action_envelopes")
    op.drop_index("ix_orchestration_steps_user_created", table_name="orchestration_steps")
    op.drop_index("ix_orchestration_steps_workflow_created", table_name="orchestration_steps")
    op.drop_table("orchestration_steps")
    op.drop_table("orchestration_plans")
    op.drop_index("ix_orchestration_routing", table_name="orchestration_workflows")
    op.drop_index("ix_orchestration_task", table_name="orchestration_workflows")
    op.drop_index("ix_orchestration_user_state_created", table_name="orchestration_workflows")
    op.drop_table("orchestration_workflows")
