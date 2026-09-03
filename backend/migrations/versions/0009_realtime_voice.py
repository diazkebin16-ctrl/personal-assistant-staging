"""Add scoped realtime voice sessions and idempotent turn metadata.

Revision ID: 0009_realtime_voice
Revises: 0008_text_assistant
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_realtime_voice"
down_revision: str | None = "0008_text_assistant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SESSION_STATES = (
    "'IDLE','CONNECTING','LISTENING','PROCESSING','SPEAKING','INTERRUPTING',"
    "'RECONNECTING','ENDED','FAILED'"
)
_TURN_STATES = "'PROCESSING','COMPLETED','INTERRUPTED','FAILED'"


def upgrade() -> None:
    op.create_table(
        "voice_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("auth_session_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "IDLE",
                "CONNECTING",
                "LISTENING",
                "PROCESSING",
                "SPEAKING",
                "INTERRUPTING",
                "RECONNECTING",
                "ENDED",
                "FAILED",
                name="voicesessionstate",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "authentication_level",
            sa.Enum(
                "AAL1",
                "AAL2",
                "UNKNOWN",
                name="authenticationlevel",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("credential_hash", sa.String(length=64), nullable=False),
        sa.Column("credential_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("routing_decision_id", sa.Uuid(), nullable=False),
        sa.Column("provider_key", sa.String(length=128), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("voice_profile", sa.String(length=64), nullable=False),
        sa.Column(
            "effective_sensitivity",
            sa.Enum(
                "PUBLIC",
                "INTERNAL",
                "PRIVATE",
                "SENSITIVE",
                "CRITICAL",
                name="datasensitivity",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("reconnect_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(f"state IN ({_SESSION_STATES})", name="ck_voice_session_state"),
        sa.CheckConstraint("length(credential_hash) = 64", name="ck_voice_credential_hash"),
        sa.CheckConstraint("reconnect_count BETWEEN 0 AND 3", name="ck_voice_reconnect_count"),
        sa.CheckConstraint("version >= 1", name="ck_voice_session_version"),
        sa.CheckConstraint("length(provider_key) BETWEEN 2 AND 128", name="ck_voice_provider_key"),
        sa.CheckConstraint("length(model_id) BETWEEN 2 AND 128", name="ck_voice_model_id"),
        sa.CheckConstraint("length(voice_profile) BETWEEN 2 AND 64", name="ck_voice_profile"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["auth_session_id"], ["auth_sessions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["routing_decision_id"], ["ai_routing_decisions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_voice_sessions_user_created", "voice_sessions", ["user_id", "created_at"])
    op.create_index("ix_voice_sessions_device_state", "voice_sessions", ["device_id", "state"])

    op.create_table(
        "voice_turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("logical_turn_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("transcript_sha256", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PROCESSING",
                "COMPLETED",
                "INTERRUPTED",
                "FAILED",
                name="voiceturnstatus",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("user_message_id", sa.Uuid(), nullable=True),
        sa.Column("assistant_message_id", sa.Uuid(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("interrupted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(f"status IN ({_TURN_STATES})", name="ck_voice_turn_status"),
        sa.CheckConstraint(
            "length(logical_turn_id) BETWEEN 8 AND 128", name="ck_voice_turn_logical_id"
        ),
        sa.CheckConstraint(
            "length(idempotency_key) BETWEEN 8 AND 128", name="ck_voice_turn_idempotency"
        ),
        sa.CheckConstraint("length(transcript_sha256) = 64", name="ck_voice_transcript_hash"),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 10000)",
            name="ck_voice_turn_confidence",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["voice_sessions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["user_message_id"], ["conversation_messages.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["assistant_message_id"], ["conversation_messages.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "logical_turn_id", name="uq_voice_turn_session_logical"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_voice_turn_user_idempotency"),
    )
    op.create_index("ix_voice_turns_session_created", "voice_turns", ["session_id", "created_at"])

    if op.get_bind().dialect.name == "postgresql":
        for table in ("voice_sessions", "voice_turns"):
            op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
            op.execute(f"REVOKE ALL ON TABLE public.{table} FROM anon, authenticated")


def downgrade() -> None:
    op.drop_index("ix_voice_turns_session_created", table_name="voice_turns")
    op.drop_table("voice_turns")
    op.drop_index("ix_voice_sessions_device_state", table_name="voice_sessions")
    op.drop_index("ix_voice_sessions_user_created", table_name="voice_sessions")
    op.drop_table("voice_sessions")
