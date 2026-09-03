"""Create the Phase 2 permissions, risk, confirmation, and audit core.

Revision ID: 0002_permissions_risk_audit
Revises: 0001_identity_auth
Create Date: 2026-09-01
"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "0002_permissions_risk_audit"
down_revision: str | None = "0001_identity_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_STATEMENTS = (
    "ALTER TABLE public.capabilities ENABLE ROW LEVEL SECURITY",
    "REVOKE ALL ON TABLE public.capabilities FROM anon, authenticated",
    "GRANT SELECT ON TABLE public.capabilities TO authenticated",
    """
    CREATE POLICY capabilities_select_enabled
    ON public.capabilities
    FOR SELECT
    TO authenticated
    USING (enabled = true)
    """,
    "ALTER TABLE public.permissions ENABLE ROW LEVEL SECURITY",
    "REVOKE ALL ON TABLE public.permissions FROM anon, authenticated",
    "GRANT SELECT ON TABLE public.permissions TO authenticated",
    """
    CREATE POLICY permissions_select_own
    ON public.permissions
    FOR SELECT
    TO authenticated
    USING (
        (SELECT auth.uid()) IS NOT NULL
        AND EXISTS (
            SELECT 1 FROM public.users owner
            WHERE owner.id = permissions.user_id
              AND owner.auth_user_id = (SELECT auth.uid())
        )
    )
    """,
    "ALTER TABLE public.authorization_decisions ENABLE ROW LEVEL SECURITY",
    "REVOKE ALL ON TABLE public.authorization_decisions FROM anon, authenticated",
    "GRANT SELECT ON TABLE public.authorization_decisions TO authenticated",
    """
    CREATE POLICY authorization_decisions_select_own
    ON public.authorization_decisions
    FOR SELECT
    TO authenticated
    USING (
        (SELECT auth.uid()) IS NOT NULL
        AND EXISTS (
            SELECT 1 FROM public.users owner
            WHERE owner.id = authorization_decisions.user_id
              AND owner.auth_user_id = (SELECT auth.uid())
        )
    )
    """,
    "ALTER TABLE public.confirmation_requests ENABLE ROW LEVEL SECURITY",
    "REVOKE ALL ON TABLE public.confirmation_requests FROM anon, authenticated",
    "GRANT SELECT ON TABLE public.confirmation_requests TO authenticated",
    """
    CREATE POLICY confirmation_requests_select_own
    ON public.confirmation_requests
    FOR SELECT
    TO authenticated
    USING (
        (SELECT auth.uid()) IS NOT NULL
        AND EXISTS (
            SELECT 1 FROM public.users owner
            WHERE owner.id = confirmation_requests.user_id
              AND owner.auth_user_id = (SELECT auth.uid())
        )
    )
    """,
    "ALTER TABLE public.audit_events ENABLE ROW LEVEL SECURITY",
    "REVOKE ALL ON TABLE public.audit_events FROM anon, authenticated",
    "GRANT SELECT ON TABLE public.audit_events TO authenticated",
    """
    CREATE POLICY audit_events_select_own
    ON public.audit_events
    FOR SELECT
    TO authenticated
    USING (
        (SELECT auth.uid()) IS NOT NULL
        AND EXISTS (
            SELECT 1 FROM public.users owner
            WHERE owner.id = audit_events.user_id
              AND owner.auth_user_id = (SELECT auth.uid())
        )
    )
    """,
)

_CAPABILITIES = (
    (
        UUID("00000000-0000-4000-8000-000000000201"),
        "device.read",
        "Read devices",
        "Read owned device metadata",
        "device",
        1,
        False,
        False,
        False,
        True,
    ),
    (
        UUID("00000000-0000-4000-8000-000000000202"),
        "device.manage",
        "Manage devices",
        "Manage owned devices",
        "device",
        2,
        False,
        False,
        True,
        True,
    ),
    (
        UUID("00000000-0000-4000-8000-000000000203"),
        "notification.send",
        "Send notification",
        "Propose an external notification",
        "communication",
        3,
        True,
        False,
        False,
        True,
    ),
    (
        UUID("00000000-0000-4000-8000-000000000204"),
        "data.delete",
        "Delete data",
        "Delete owned application data",
        "data",
        4,
        False,
        False,
        True,
        True,
    ),
    (
        UUID("00000000-0000-4000-8000-000000000205"),
        "finance.read",
        "Read finance",
        "Read authorized financial information",
        "finance",
        2,
        False,
        True,
        False,
        True,
    ),
    (
        UUID("00000000-0000-4000-8000-000000000206"),
        "finance.execute",
        "Execute finance",
        "Financial execution boundary",
        "finance",
        5,
        True,
        True,
        False,
        True,
    ),
)


def upgrade() -> None:
    """Add Phase 2 without altering or rebuilding Phase 1 data."""
    op.create_table(
        "capabilities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("default_risk_level", sa.Integer(), nullable=False),
        sa.Column("external_side_effect", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("financial", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("data_destructive", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("privacy_impact", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
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
        sa.CheckConstraint("default_risk_level BETWEEN 0 AND 5", name="ck_capabilities_risk_level"),
        sa.CheckConstraint("length(key) BETWEEN 3 AND 128", name="ck_capabilities_key_length"),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 100", name="ck_capabilities_name_length"),
        sa.CheckConstraint(
            "length(description) BETWEEN 1 AND 500",
            name="ck_capabilities_description_length",
        ),
        sa.CheckConstraint(
            "length(category) BETWEEN 1 AND 64", name="ck_capabilities_category_length"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_capabilities_key"),
    )

    op.create_table(
        "permissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("capability_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("scope_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "REVOKED",
                "EXPIRED",
                name="permission_status",
                native_enum=False,
                create_constraint=False,
            ),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column(
            "confirmation_policy",
            sa.Enum(
                "NEVER",
                "ONCE",
                "EVERY_TIME",
                "HIGH_RISK_ONLY",
                name="confirmation_policy",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("auto_execute", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "grant_source",
            sa.Enum(
                "USER_EXPLICIT",
                "SYSTEM_DEFAULT",
                "MIGRATION",
                name="permission_grant_source",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_once_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
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
        sa.CheckConstraint("status IN ('ACTIVE', 'REVOKED', 'EXPIRED')", name="permission_status"),
        sa.CheckConstraint(
            "confirmation_policy IN ('NEVER', 'ONCE', 'EVERY_TIME', 'HIGH_RISK_ONLY')",
            name="confirmation_policy",
        ),
        sa.CheckConstraint(
            "grant_source IN ('USER_EXPLICIT', 'SYSTEM_DEFAULT', 'MIGRATION')",
            name="permission_grant_source",
        ),
        sa.CheckConstraint("length(scope_digest) = 64", name="ck_permissions_scope_digest"),
        sa.CheckConstraint("length(CAST(scope AS TEXT)) <= 8192", name="ck_permissions_scope_size"),
        sa.CheckConstraint(
            "reason IS NULL OR length(reason) BETWEEN 1 AND 500",
            name="ck_permissions_reason_length",
        ),
        sa.ForeignKeyConstraint(["capability_id"], ["capabilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_permissions_device_id", "permissions", ["device_id"], unique=False)
    op.create_index("ix_permissions_expires_at", "permissions", ["expires_at"], unique=False)
    op.create_index(
        "ix_permissions_user_capability_status",
        "permissions",
        ["user_id", "capability_id", "status"],
        unique=False,
    )

    op.create_table(
        "authorization_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("permission_id", sa.Uuid(), nullable=True),
        sa.Column("capability_key", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("scope_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "decision",
            sa.Enum(
                "ALLOW",
                "DENY",
                "REQUIRE_CONFIRMATION",
                name="authorization_decision",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("risk_level", sa.Integer(), nullable=False),
        sa.Column("confirmation_required", sa.Boolean(), nullable=False),
        sa.Column("scope_match", sa.Boolean(), nullable=False),
        sa.Column("financial_guard_triggered", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision IN ('ALLOW', 'DENY', 'REQUIRE_CONFIRMATION')",
            name="authorization_decision",
        ),
        sa.CheckConstraint("risk_level BETWEEN 0 AND 5", name="ck_decisions_risk_level"),
        sa.CheckConstraint("length(scope_digest) = 64", name="ck_decisions_scope_digest"),
        sa.CheckConstraint("length(CAST(scope AS TEXT)) <= 8192", name="ck_decisions_scope_size"),
        sa.CheckConstraint(
            "length(CAST(reason_codes AS TEXT)) <= 4096",
            name="ck_decisions_reason_codes_size",
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_decisions_permission_id", "authorization_decisions", ["permission_id"], unique=False
    )
    op.create_index(
        "ix_decisions_user_created",
        "authorization_decisions",
        ["user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "confirmation_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("authorization_decision_id", sa.Uuid(), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.Column("capability_key", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("scope_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "APPROVED",
                "REJECTED",
                "EXPIRED",
                name="confirmation_status",
                native_enum=False,
                create_constraint=False,
            ),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED')",
            name="confirmation_status",
        ),
        sa.CheckConstraint("length(scope_digest) = 64", name="ck_confirmations_scope_digest"),
        sa.CheckConstraint("expires_at > requested_at", name="ck_confirmations_expiry"),
        sa.ForeignKeyConstraint(
            ["authorization_decision_id"],
            ["authorization_decisions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "authorization_decision_id", name="uq_confirmations_authorization_decision"
        ),
    )
    op.create_index(
        "ix_confirmations_expires_at", "confirmation_requests", ["expires_at"], unique=False
    )
    op.create_index(
        "ix_confirmations_user_status",
        "confirmation_requests",
        ["user_id", "status"],
        unique=False,
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column(
            "actor_type",
            sa.Enum(
                "USER",
                "SYSTEM",
                "AI",
                "AUTOMATION",
                "DEVICE",
                name="audit_actor_type",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.Enum(
                "PERMISSION_GRANTED",
                "PERMISSION_REVOKED",
                "PERMISSION_EXPIRED_OBSERVED",
                "AUTHORIZATION_ALLOWED",
                "AUTHORIZATION_DENIED",
                "CONFIRMATION_REQUESTED",
                "CONFIRMATION_APPROVED",
                "CONFIRMATION_REJECTED",
                "FINANCIAL_GUARD_TRIGGERED",
                name="audit_event_type",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("capability_key", sa.String(length=128), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=True),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("risk_level", sa.Integer(), nullable=True),
        sa.Column("permission_id", sa.Uuid(), nullable=True),
        sa.Column("authorization_decision_id", sa.Uuid(), nullable=True),
        sa.Column("confirmation_id", sa.Uuid(), nullable=True),
        sa.Column(
            "result",
            sa.Enum(
                "RECORDED",
                "ALLOWED",
                "DENIED",
                "REQUESTED",
                "APPROVED",
                "REJECTED",
                name="audit_result",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("execution_id", sa.Uuid(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "actor_type IN ('USER', 'SYSTEM', 'AI', 'AUTOMATION', 'DEVICE')",
            name="audit_actor_type",
        ),
        sa.CheckConstraint(
            "event_type IN ("
            "'PERMISSION_GRANTED', 'PERMISSION_REVOKED', 'PERMISSION_EXPIRED_OBSERVED', "
            "'AUTHORIZATION_ALLOWED', 'AUTHORIZATION_DENIED', 'CONFIRMATION_REQUESTED', "
            "'CONFIRMATION_APPROVED', 'CONFIRMATION_REJECTED', "
            "'FINANCIAL_GUARD_TRIGGERED')",
            name="audit_event_type",
        ),
        sa.CheckConstraint(
            "result IN ('RECORDED', 'ALLOWED', 'DENIED', 'REQUESTED', 'APPROVED', 'REJECTED')",
            name="audit_result",
        ),
        sa.CheckConstraint(
            "risk_level IS NULL OR risk_level BETWEEN 0 AND 5", name="ck_audit_risk_level"
        ),
        sa.CheckConstraint(
            "length(CAST(reason_codes AS TEXT)) <= 4096", name="ck_audit_reason_codes_size"
        ),
        sa.CheckConstraint("length(CAST(metadata AS TEXT)) <= 8192", name="ck_audit_metadata_size"),
        sa.ForeignKeyConstraint(
            ["authorization_decision_id"], ["authorization_decisions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["confirmation_id"], ["confirmation_requests.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["auth_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_decision_id", "audit_events", ["authorization_decision_id"], unique=False
    )
    op.create_index("ix_audit_permission_id", "audit_events", ["permission_id"], unique=False)
    op.create_index(
        "ix_audit_user_timestamp", "audit_events", ["user_id", "timestamp"], unique=False
    )

    capability_table = sa.table(
        "capabilities",
        sa.column("id", sa.Uuid()),
        sa.column("key", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("category", sa.String()),
        sa.column("default_risk_level", sa.Integer()),
        sa.column("external_side_effect", sa.Boolean()),
        sa.column("financial", sa.Boolean()),
        sa.column("data_destructive", sa.Boolean()),
        sa.column("privacy_impact", sa.Boolean()),
        sa.column("enabled", sa.Boolean()),
    )
    op.bulk_insert(
        capability_table,
        [
            {
                "id": item[0],
                "key": item[1],
                "name": item[2],
                "description": item[3],
                "category": item[4],
                "default_risk_level": item[5],
                "external_side_effect": item[6],
                "financial": item[7],
                "data_destructive": item[8],
                "privacy_impact": item[9],
                "enabled": True,
            }
            for item in _CAPABILITIES
        ],
    )

    if op.get_bind().dialect.name == "postgresql":
        for statement in _RLS_STATEMENTS:
            op.execute(statement)


def downgrade() -> None:
    """Remove only Phase 2 tables; Phase 1 identity data remains intact."""
    op.drop_index("ix_audit_user_timestamp", table_name="audit_events")
    op.drop_index("ix_audit_permission_id", table_name="audit_events")
    op.drop_index("ix_audit_decision_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_confirmations_user_status", table_name="confirmation_requests")
    op.drop_index("ix_confirmations_expires_at", table_name="confirmation_requests")
    op.drop_table("confirmation_requests")
    op.drop_index("ix_decisions_user_created", table_name="authorization_decisions")
    op.drop_index("ix_decisions_permission_id", table_name="authorization_decisions")
    op.drop_table("authorization_decisions")
    op.drop_index("ix_permissions_user_capability_status", table_name="permissions")
    op.drop_index("ix_permissions_expires_at", table_name="permissions")
    op.drop_index("ix_permissions_device_id", table_name="permissions")
    op.drop_table("permissions")
    op.drop_table("capabilities")
