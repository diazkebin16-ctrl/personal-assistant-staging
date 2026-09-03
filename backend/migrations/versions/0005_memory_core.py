"""Create the Phase 4 Memory Core and restrictive RLS foundation.

Revision ID: 0005_memory_core
Revises: 0004_task_engine
Create Date: 2026-09-01
"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "0005_memory_core"
down_revision: str | None = "0004_task_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MEMORY_CLASSES = (
    "'TEMPORARY_CONTEXT', 'OPERATIONAL', 'PERSISTENT_PREFERENCE', "
    "'HISTORICAL_DECISION', 'DISCARDABLE'"
)
_MEMORY_STATUSES = "'ACTIVE', 'ARCHIVED', 'EXPIRED', 'DELETED'"
_MEMORY_SOURCES = "'USER_EXPLICIT', 'SYSTEM', 'TASK', 'DEVICE', 'IMPORT', 'FUTURE_AI_PROPOSAL'"
_SENSITIVITY = "'PUBLIC', 'INTERNAL', 'PRIVATE', 'SENSITIVE', 'CRITICAL'"
_PHASE3_AUDIT_EVENTS = (
    "'PERMISSION_GRANTED', 'PERMISSION_REVOKED', 'PERMISSION_EXPIRED_OBSERVED', "
    "'AUTHORIZATION_ALLOWED', 'AUTHORIZATION_DENIED', 'CONFIRMATION_REQUESTED', "
    "'CONFIRMATION_APPROVED', 'CONFIRMATION_REJECTED', 'FINANCIAL_GUARD_TRIGGERED', "
    "'TASK_CREATED', 'TASK_CANCELLED', 'TASK_CLAIMED'"
)
_PHASE4_AUDIT_EVENTS = (
    _PHASE3_AUDIT_EVENTS
    + ", 'MEMORY_CREATED', 'MEMORY_UPDATED', 'MEMORY_ARCHIVED', 'MEMORY_DELETED'"
)

_MEMORY_CAPABILITIES = (
    (
        UUID("00000000-0000-0000-0000-000000000301"),
        "memory.read",
        "Read memory",
        "Read owner-scoped active or historical memory",
        2,
        ["read"],
        False,
        False,
        False,
        True,
    ),
    (
        UUID("00000000-0000-0000-0000-000000000302"),
        "memory.write",
        "Write memory",
        "Create, update, or archive owner-scoped memory",
        3,
        ["archive", "create", "update"],
        False,
        False,
        False,
        True,
    ),
    (
        UUID("00000000-0000-0000-0000-000000000303"),
        "memory.delete",
        "Delete memory",
        "Privacy-delete owner-scoped memory",
        4,
        ["delete"],
        False,
        False,
        True,
        True,
    ),
)

_RLS_STATEMENTS = (
    "ALTER TABLE public.memory_records ENABLE ROW LEVEL SECURITY",
    "REVOKE ALL ON TABLE public.memory_records FROM anon, authenticated",
    "GRANT SELECT ON TABLE public.memory_records TO authenticated",
    """
    CREATE POLICY memory_records_select_own
    ON public.memory_records FOR SELECT TO authenticated
    USING (
        status != 'DELETED'
        AND (SELECT auth.uid()) IS NOT NULL
        AND EXISTS (
            SELECT 1 FROM public.users owner
            WHERE owner.id = memory_records.user_id
              AND owner.auth_user_id = (SELECT auth.uid())
        )
    )
    """,
    "ALTER TABLE public.memory_revisions ENABLE ROW LEVEL SECURITY",
    "REVOKE ALL ON TABLE public.memory_revisions FROM anon, authenticated",
    "GRANT SELECT ON TABLE public.memory_revisions TO authenticated",
    """
    CREATE POLICY memory_revisions_select_own
    ON public.memory_revisions FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.memory_records memory
            JOIN public.users owner ON owner.id = memory.user_id
            WHERE memory.id = memory_revisions.memory_id
              AND memory.status != 'DELETED'
              AND owner.auth_user_id = (SELECT auth.uid())
        )
    )
    """,
    "ALTER TABLE public.memory_events ENABLE ROW LEVEL SECURITY",
    "REVOKE ALL ON TABLE public.memory_events FROM anon, authenticated",
    "GRANT SELECT ON TABLE public.memory_events TO authenticated",
    """
    CREATE POLICY memory_events_select_own
    ON public.memory_events FOR SELECT TO authenticated
    USING (
        (SELECT auth.uid()) IS NOT NULL
        AND EXISTS (
            SELECT 1 FROM public.users owner
            WHERE owner.id = memory_events.user_id
              AND owner.auth_user_id = (SELECT auth.uid())
        )
    )
    """,
)


def upgrade() -> None:
    """Add Memory Core without rewriting certified Phase 0-3 migrations."""
    op.create_table(
        "memory_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source_device_id", sa.Uuid(), nullable=True),
        sa.Column(
            "memory_class",
            sa.Enum(
                "TEMPORARY_CONTEXT",
                "OPERATIONAL",
                "PERSISTENT_PREFERENCE",
                "HISTORICAL_DECISION",
                "DISCARDABLE",
                name="memory_class",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "ARCHIVED",
                "EXPIRED",
                "DELETED",
                name="memory_status",
                native_enum=False,
                create_constraint=False,
            ),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column(
            "source_type",
            sa.Enum(
                "USER_EXPLICIT",
                "SYSTEM",
                "TASK",
                "DEVICE",
                "IMPORT",
                "FUTURE_AI_PROPOSAL",
                name="memory_source_type",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("normalized_content", sa.Text(), nullable=True),
        sa.Column("summary", sa.String(length=1000), nullable=True),
        sa.Column("subject", sa.String(length=200), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False),
        sa.Column(
            "sensitivity",
            sa.Enum(
                "PUBLIC",
                "INTERNAL",
                "PRIVATE",
                "SENSITIVE",
                "CRITICAL",
                name="memory_sensitivity",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("deduplication_key", sa.String(length=64), nullable=True),
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
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.CheckConstraint(f"memory_class IN ({_MEMORY_CLASSES})", name="memory_class"),
        sa.CheckConstraint(f"status IN ({_MEMORY_STATUSES})", name="memory_status"),
        sa.CheckConstraint(f"source_type IN ({_MEMORY_SOURCES})", name="memory_source_type"),
        sa.CheckConstraint(f"sensitivity IN ({_SENSITIVITY})", name="memory_sensitivity"),
        sa.CheckConstraint("length(content) BETWEEN 1 AND 16000", name="ck_memory_content_length"),
        sa.CheckConstraint(
            "normalized_content IS NULL OR length(normalized_content) BETWEEN 1 AND 16000",
            name="ck_memory_normalized_length",
        ),
        sa.CheckConstraint(
            "summary IS NULL OR length(summary) BETWEEN 1 AND 1000",
            name="ck_memory_summary_length",
        ),
        sa.CheckConstraint(
            "subject IS NULL OR length(subject) BETWEEN 1 AND 200",
            name="ck_memory_subject_length",
        ),
        sa.CheckConstraint(
            "source_reference IS NULL OR length(source_reference) BETWEEN 1 AND 255",
            name="ck_memory_source_reference_length",
        ),
        sa.CheckConstraint("confidence BETWEEN 0 AND 100", name="ck_memory_confidence"),
        sa.CheckConstraint("importance BETWEEN 0 AND 100", name="ck_memory_importance"),
        sa.CheckConstraint("length(fingerprint) = 64", name="ck_memory_fingerprint"),
        sa.CheckConstraint(
            "deduplication_key IS NULL OR length(deduplication_key) = 64",
            name="ck_memory_deduplication_key",
        ),
        sa.CheckConstraint("version >= 1", name="ck_memory_version_positive"),
        sa.CheckConstraint(
            "memory_class != 'TEMPORARY_CONTEXT' OR expires_at IS NOT NULL",
            name="ck_temporary_memory_expires",
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > created_at", name="ck_memory_expiry_after_creation"
        ),
        sa.CheckConstraint(
            "status != 'ARCHIVED' OR archived_at IS NOT NULL", name="ck_archived_memory_timestamp"
        ),
        sa.CheckConstraint(
            "status != 'EXPIRED' OR expires_at IS NOT NULL", name="ck_expired_memory_timestamp"
        ),
        sa.CheckConstraint(
            "status != 'DELETED' OR deleted_at IS NOT NULL", name="ck_deleted_memory_timestamp"
        ),
        sa.CheckConstraint(
            "length(CAST(metadata AS TEXT)) <= 4096", name="ck_memory_metadata_size"
        ),
        sa.ForeignKeyConstraint(["source_device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_expires_at", "memory_records", ["expires_at"])
    op.create_index(
        "ix_memory_user_class_updated", "memory_records", ["user_id", "memory_class", "updated_at"]
    )
    op.create_index(
        "ix_memory_user_status_created", "memory_records", ["user_id", "status", "created_at"]
    )
    op.create_index("ix_memory_user_subject", "memory_records", ["user_id", "subject"])
    op.create_index(
        "uq_memory_active_deduplication",
        "memory_records",
        ["user_id", "memory_class", "deduplication_key"],
        unique=True,
        sqlite_where=sa.text("status = 'ACTIVE' AND deduplication_key IS NOT NULL"),
        postgresql_where=sa.text("status = 'ACTIVE' AND deduplication_key IS NOT NULL"),
    )

    op.create_table(
        "memory_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("memory_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column(
            "memory_class",
            sa.Enum(
                "TEMPORARY_CONTEXT",
                "OPERATIONAL",
                "PERSISTENT_PREFERENCE",
                "HISTORICAL_DECISION",
                "DISCARDABLE",
                name="memory_class",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "source_type",
            sa.Enum(
                "USER_EXPLICIT",
                "SYSTEM",
                "TASK",
                "DEVICE",
                "IMPORT",
                "FUTURE_AI_PROPOSAL",
                name="memory_source_type",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("normalized_content", sa.Text(), nullable=True),
        sa.Column("summary", sa.String(length=1000), nullable=True),
        sa.Column("subject", sa.String(length=200), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False),
        sa.Column(
            "sensitivity",
            sa.Enum(
                "PUBLIC",
                "INTERNAL",
                "PRIVATE",
                "SENSITIVE",
                "CRITICAL",
                name="memory_sensitivity",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "actor_type",
            sa.Enum(
                "USER",
                "SYSTEM",
                "DEVICE",
                name="memory_actor_type",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.CheckConstraint(f"memory_class IN ({_MEMORY_CLASSES})", name="revision_memory_class"),
        sa.CheckConstraint(
            f"source_type IN ({_MEMORY_SOURCES})", name="revision_memory_source_type"
        ),
        sa.CheckConstraint(f"sensitivity IN ({_SENSITIVITY})", name="revision_memory_sensitivity"),
        sa.CheckConstraint(
            "actor_type IN ('USER', 'SYSTEM', 'DEVICE')", name="revision_memory_actor_type"
        ),
        sa.CheckConstraint("revision_number >= 1", name="ck_memory_revision_positive"),
        sa.CheckConstraint(
            "length(content) BETWEEN 1 AND 16000", name="ck_revision_content_length"
        ),
        sa.CheckConstraint(
            "normalized_content IS NULL OR length(normalized_content) BETWEEN 1 AND 16000",
            name="ck_revision_normalized_length",
        ),
        sa.CheckConstraint("length(fingerprint) = 64", name="ck_revision_fingerprint"),
        sa.CheckConstraint(
            "length(CAST(metadata AS TEXT)) <= 4096", name="ck_revision_metadata_size"
        ),
        sa.ForeignKeyConstraint(["memory_id"], ["memory_records.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_memory_revisions_recorded", "memory_revisions", ["memory_id", "recorded_at"]
    )
    op.create_index(
        "uq_memory_revision_number",
        "memory_revisions",
        ["memory_id", "revision_number"],
        unique=True,
    )

    op.create_table(
        "memory_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("memory_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "CREATED",
                "UPDATED",
                "ARCHIVED",
                "EXPIRED",
                "DELETED",
                "DEDUPLICATED",
                name="memory_event_type",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "from_status",
            sa.Enum(
                "ACTIVE",
                "ARCHIVED",
                "EXPIRED",
                "DELETED",
                name="memory_status",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "to_status",
            sa.Enum(
                "ACTIVE",
                "ARCHIVED",
                "EXPIRED",
                "DELETED",
                name="memory_status",
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
        sa.Column(
            "actor_type",
            sa.Enum(
                "USER",
                "SYSTEM",
                "DEVICE",
                name="memory_actor_type",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('CREATED', 'UPDATED', 'ARCHIVED', 'EXPIRED', 'DELETED', "
            "'DEDUPLICATED')",
            name="memory_event_type",
        ),
        sa.CheckConstraint("actor_type IN ('USER', 'SYSTEM', 'DEVICE')", name="memory_actor_type"),
        sa.CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_MEMORY_STATUSES})",
            name="memory_event_from_status",
        ),
        sa.CheckConstraint(f"to_status IN ({_MEMORY_STATUSES})", name="memory_event_to_status"),
        sa.CheckConstraint("length(reason_code) BETWEEN 1 AND 128", name="ck_memory_event_reason"),
        sa.CheckConstraint(
            "length(CAST(metadata AS TEXT)) <= 4096", name="ck_memory_event_metadata_size"
        ),
        sa.ForeignKeyConstraint(["memory_id"], ["memory_records.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_memory_events_memory_timestamp", "memory_events", ["memory_id", "timestamp"]
    )
    op.create_index("ix_memory_events_user_timestamp", "memory_events", ["user_id", "timestamp"])

    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.drop_constraint("audit_event_type", type_="check")
        batch_op.create_check_constraint(
            "audit_event_type", f"event_type IN ({_PHASE4_AUDIT_EVENTS})"
        )

    capability = sa.table(
        "capabilities",
        sa.column("id", sa.Uuid()),
        sa.column("key", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("category", sa.String()),
        sa.column("default_risk_level", sa.Integer()),
        sa.column("allowed_actions", sa.JSON()),
        sa.column("external_side_effect", sa.Boolean()),
        sa.column("financial", sa.Boolean()),
        sa.column("data_destructive", sa.Boolean()),
        sa.column("privacy_impact", sa.Boolean()),
        sa.column("enabled", sa.Boolean()),
    )
    op.bulk_insert(
        capability,
        [
            {
                "id": item[0],
                "key": item[1],
                "name": item[2],
                "description": item[3],
                "category": "memory",
                "default_risk_level": item[4],
                "allowed_actions": item[5],
                "external_side_effect": item[6],
                "financial": item[7],
                "data_destructive": item[8],
                "privacy_impact": item[9],
                "enabled": True,
            }
            for item in _MEMORY_CAPABILITIES
        ],
    )

    if op.get_bind().dialect.name == "postgresql":
        for statement in _RLS_STATEMENTS:
            op.execute(statement)


def downgrade() -> None:
    """Remove Phase 4 objects; populated memory capability grants must be revoked first."""
    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.drop_constraint("audit_event_type", type_="check")
        batch_op.create_check_constraint(
            "audit_event_type", f"event_type IN ({_PHASE3_AUDIT_EVENTS})"
        )

    op.drop_index("ix_memory_events_user_timestamp", table_name="memory_events")
    op.drop_index("ix_memory_events_memory_timestamp", table_name="memory_events")
    op.drop_table("memory_events")
    op.drop_index("uq_memory_revision_number", table_name="memory_revisions")
    op.drop_index("ix_memory_revisions_recorded", table_name="memory_revisions")
    op.drop_table("memory_revisions")
    op.drop_index("uq_memory_active_deduplication", table_name="memory_records")
    op.drop_index("ix_memory_user_subject", table_name="memory_records")
    op.drop_index("ix_memory_user_status_created", table_name="memory_records")
    op.drop_index("ix_memory_user_class_updated", table_name="memory_records")
    op.drop_index("ix_memory_expires_at", table_name="memory_records")
    op.drop_table("memory_records")

    capability = sa.table("capabilities", sa.column("key", sa.String()))
    op.execute(
        sa.delete(capability).where(
            capability.c.key.in_([item[1] for item in _MEMORY_CAPABILITIES])
        )
    )
