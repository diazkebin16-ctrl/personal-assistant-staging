"""Add durable owner-scoped Text Assistant conversations.

Revision ID: 0008_text_assistant
Revises: 0007_orchestrator
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_text_assistant"
down_revision: str | None = "0007_orchestrator"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OUTCOMES = (
    "'ANSWERED','MEMORY_SAVED','MEMORY_RECALLED','MEMORY_PERMISSION_REQUIRED',"
    "'MEMORY_TARGET_REQUIRED','MEMORY_CONFIRMATION_REQUIRED','MEMORY_DELETED',"
    "'ACTION_WAITING_PERMISSION',"
    "'ACTION_WAITING_CONFIRMATION','ACTION_READY_FOR_FUTURE_EXECUTION','ACTION_DENIED',"
    "'ACTION_UNSUPPORTED','FAILED'"
)


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("next_sequence", sa.Integer(), server_default="1", nullable=False),
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
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "title IS NULL OR length(title) BETWEEN 1 AND 200", name="ck_conversation_title"
        ),
        sa.CheckConstraint("version >= 1", name="ck_conversation_version"),
        sa.CheckConstraint("next_sequence >= 1", name="ck_conversation_next_sequence"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_user_updated", "conversations", ["user_id", "updated_at"])

    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "USER", "ASSISTANT", name="messagerole", native_enum=False, create_constraint=False
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "COMPLETED",
                "FAILED",
                name="messagestatus",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "outcome",
            sa.Enum(
                "ANSWERED",
                "MEMORY_SAVED",
                "MEMORY_RECALLED",
                "MEMORY_PERMISSION_REQUIRED",
                "MEMORY_TARGET_REQUIRED",
                "MEMORY_CONFIRMATION_REQUIRED",
                "MEMORY_DELETED",
                "ACTION_WAITING_PERMISSION",
                "ACTION_WAITING_CONFIRMATION",
                "ACTION_READY_FOR_FUTURE_EXECUTION",
                "ACTION_DENIED",
                "ACTION_UNSUPPORTED",
                "FAILED",
                name="assistantoutcome",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=True,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "sensitivity",
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
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("reply_to_message_id", sa.Uuid(), nullable=True),
        sa.Column("routing_decision_id", sa.Uuid(), nullable=True),
        sa.Column("orchestration_id", sa.Uuid(), nullable=True),
        sa.Column("confirmation_request_id", sa.Uuid(), nullable=True),
        sa.Column("memory_id", sa.Uuid(), nullable=True),
        sa.Column("reason_code", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("sequence >= 1", name="ck_message_sequence"),
        sa.CheckConstraint("length(content) BETWEEN 1 AND 100000", name="ck_message_content"),
        sa.CheckConstraint("role IN ('USER','ASSISTANT')", name="ck_message_role"),
        sa.CheckConstraint("status IN ('COMPLETED','FAILED')", name="ck_message_status"),
        sa.CheckConstraint(
            "sensitivity IN ('PUBLIC','INTERNAL','PRIVATE','SENSITIVE','CRITICAL')",
            name="ck_message_sensitivity",
        ),
        sa.CheckConstraint(
            f"outcome IS NULL OR outcome IN ({_OUTCOMES})", name="ck_message_outcome"
        ),
        sa.CheckConstraint(
            "request_fingerprint IS NULL OR length(request_fingerprint) = 64",
            name="ck_message_request_fingerprint",
        ),
        sa.CheckConstraint(
            "(role = 'USER' AND idempotency_key IS NOT NULL AND request_fingerprint IS NOT NULL "
            "AND outcome IS NULL AND reply_to_message_id IS NULL AND status = 'COMPLETED') OR "
            "(role = 'ASSISTANT' AND idempotency_key IS NULL AND request_fingerprint IS NULL "
            "AND outcome IS NOT NULL AND reply_to_message_id IS NOT NULL)",
            name="ck_message_role_contract",
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["reply_to_message_id"], ["conversation_messages.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["routing_decision_id"], ["ai_routing_decisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["orchestration_id"], ["orchestration_workflows.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["confirmation_request_id"], ["confirmation_requests.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["memory_id"], ["memory_records.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "sequence", name="uq_message_conversation_sequence"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_message_user_idempotency"),
    )
    op.create_index(
        "ix_messages_conversation_sequence",
        "conversation_messages",
        ["conversation_id", "sequence"],
    )
    op.create_index("ix_messages_user_created", "conversation_messages", ["user_id", "created_at"])
    op.create_index("ix_messages_reply_to", "conversation_messages", ["reply_to_message_id"])

    if op.get_bind().dialect.name == "postgresql":
        for table in ("conversations", "conversation_messages"):
            op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"REVOKE ALL ON TABLE public.{table} FROM anon, authenticated")
            op.execute(f"GRANT SELECT ON TABLE public.{table} TO authenticated")
        op.execute("""
            CREATE POLICY conversations_select_own ON public.conversations
            FOR SELECT TO authenticated USING (EXISTS (
              SELECT 1 FROM public.users owner WHERE owner.id = conversations.user_id
              AND owner.auth_user_id = (SELECT auth.uid())))
        """)
        op.execute("""
            CREATE POLICY conversation_messages_select_own ON public.conversation_messages
            FOR SELECT TO authenticated USING (EXISTS (
              SELECT 1 FROM public.users owner WHERE owner.id = conversation_messages.user_id
              AND owner.auth_user_id = (SELECT auth.uid())))
        """)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP POLICY IF EXISTS conversation_messages_select_own ON public.conversation_messages"
        )
        op.execute("DROP POLICY IF EXISTS conversations_select_own ON public.conversations")
    op.drop_index("ix_messages_reply_to", table_name="conversation_messages")
    op.drop_index("ix_messages_user_created", table_name="conversation_messages")
    op.drop_index("ix_messages_conversation_sequence", table_name="conversation_messages")
    op.drop_table("conversation_messages")
    op.drop_index("ix_conversations_user_updated", table_name="conversations")
    op.drop_table("conversations")
