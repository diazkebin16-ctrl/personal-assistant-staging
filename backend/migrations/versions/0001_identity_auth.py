"""Create Phase 1 identity, device, session, and RLS foundation.

Revision ID: 0001_identity_auth
Revises:
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_identity_auth"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_STATEMENTS = (
    "ALTER TABLE public.users ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE public.devices ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE public.auth_sessions ENABLE ROW LEVEL SECURITY",
    "REVOKE ALL ON TABLE public.users FROM anon, authenticated",
    "REVOKE ALL ON TABLE public.devices FROM anon, authenticated",
    "REVOKE ALL ON TABLE public.auth_sessions FROM anon, authenticated",
    "GRANT SELECT ON TABLE public.users TO authenticated",
    "GRANT SELECT ON TABLE public.devices TO authenticated",
    "GRANT SELECT ON TABLE public.auth_sessions TO authenticated",
    """
    CREATE POLICY users_select_own
    ON public.users
    FOR SELECT
    TO authenticated
    USING (
        (SELECT auth.uid()) IS NOT NULL
        AND (SELECT auth.uid()) = auth_user_id
    )
    """,
    """
    CREATE POLICY devices_select_own
    ON public.devices
    FOR SELECT
    TO authenticated
    USING (
        (SELECT auth.uid()) IS NOT NULL
        AND EXISTS (
            SELECT 1
            FROM public.users owner
            WHERE owner.id = devices.user_id
              AND owner.auth_user_id = (SELECT auth.uid())
        )
    )
    """,
    """
    CREATE POLICY auth_sessions_select_own
    ON public.auth_sessions
    FOR SELECT
    TO authenticated
    USING (
        (SELECT auth.uid()) IS NOT NULL
        AND EXISTS (
            SELECT 1
            FROM public.users owner
            WHERE owner.id = auth_sessions.user_id
              AND owner.auth_user_id = (SELECT auth.uid())
        )
    )
    """,
)


def upgrade() -> None:
    """Create the non-destructive Phase 1 schema and PostgreSQL RLS policies."""
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("auth_user_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "DISABLED",
                name="user_status",
                native_enum=False,
                create_constraint=False,
            ),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "display_name IS NULL OR length(display_name) BETWEEN 1 AND 100",
            name="ck_users_display_name_length",
        ),
        sa.CheckConstraint("status IN ('ACTIVE', 'DISABLED')", name="user_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("auth_user_id", name="uq_users_auth_user_id"),
    )

    op.create_table(
        "devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_name", sa.String(length=100), nullable=False),
        sa.Column(
            "device_type",
            sa.Enum(
                "ANDROID",
                "IOS",
                "WEB",
                "DESKTOP",
                "WATCH",
                "UNKNOWN",
                name="device_type",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("device_identifier", sa.String(length=128), nullable=False),
        sa.Column("trusted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("public_key", sa.String(length=4096), nullable=True),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "length(device_name) BETWEEN 1 AND 100",
            name="ck_devices_name_length",
        ),
        sa.CheckConstraint(
            "length(platform) BETWEEN 1 AND 64",
            name="ck_devices_platform_length",
        ),
        sa.CheckConstraint(
            "length(device_identifier) BETWEEN 8 AND 128",
            name="ck_devices_identifier_length",
        ),
        sa.CheckConstraint(
            "public_key IS NULL OR length(public_key) <= 4096",
            name="ck_devices_public_key_length",
        ),
        sa.CheckConstraint(
            "length(CAST(capabilities AS TEXT)) <= 8192",
            name="ck_devices_capabilities_size",
        ),
        sa.CheckConstraint(
            "device_type IN ('ANDROID', 'IOS', 'WEB', 'DESKTOP', 'WATCH', 'UNKNOWN')",
            name="device_type",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "device_identifier", name="uq_devices_user_identifier"),
    )
    op.create_index(
        "ix_devices_user_last_seen",
        "devices",
        ["user_id", "last_seen_at"],
        unique=False,
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("auth_session_identifier", sa.String(length=255), nullable=False),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "length(auth_session_identifier) BETWEEN 1 AND 255",
            name="ck_auth_sessions_identifier_length",
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "auth_session_identifier",
            name="uq_auth_sessions_identifier",
        ),
    )
    op.create_index(
        "ix_auth_sessions_device_id",
        "auth_sessions",
        ["device_id"],
        unique=False,
    )
    op.create_index(
        "ix_auth_sessions_user_last_seen",
        "auth_sessions",
        ["user_id", "last_seen_at"],
        unique=False,
    )

    if op.get_bind().dialect.name == "postgresql":
        for statement in _RLS_STATEMENTS:
            op.execute(statement)


def downgrade() -> None:
    """Remove only the tables introduced by this revision."""
    op.drop_index("ix_auth_sessions_user_last_seen", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_device_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_devices_user_last_seen", table_name="devices")
    op.drop_table("devices")
    op.drop_table("users")
