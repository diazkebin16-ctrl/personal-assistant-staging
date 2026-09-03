"""Add cited Web Research message metadata and capability.

Revision ID: 0010_web_research
Revises: 0009_realtime_voice
Create Date: 2026-09-02
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0010_web_research"
down_revision: str | None = "0009_realtime_voice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_OUTCOMES = (
    "'ANSWERED','MEMORY_SAVED','MEMORY_RECALLED','MEMORY_PERMISSION_REQUIRED',"
    "'MEMORY_TARGET_REQUIRED','MEMORY_CONFIRMATION_REQUIRED','MEMORY_DELETED',"
    "'ACTION_WAITING_PERMISSION','ACTION_WAITING_CONFIRMATION',"
    "'ACTION_READY_FOR_FUTURE_EXECUTION','ACTION_DENIED','ACTION_UNSUPPORTED','FAILED'"
)
_RESEARCH_OUTCOMES = (
    "'RESEARCH_ANSWERED','RESEARCH_PERMISSION_REQUIRED','RESEARCH_CONFIRMATION_REQUIRED',"
    "'RESEARCH_POLICY_DENIED','RESEARCH_UNAVAILABLE','RESEARCH_INSUFFICIENT_EVIDENCE'"
)


def _replace_outcome_constraint(values: str) -> None:
    with op.batch_alter_table("conversation_messages") as batch:
        batch.drop_constraint("ck_message_outcome", type_="check")
        batch.create_check_constraint(
            "ck_message_outcome", f"outcome IS NULL OR outcome IN ({values})"
        )


def upgrade() -> None:
    with op.batch_alter_table("conversation_messages") as batch:
        batch.add_column(
            sa.Column(
                "research_citations",
                sa.JSON(),
                server_default=sa.text("'[]'"),
                nullable=False,
            )
        )
        batch.create_check_constraint(
            "ck_message_research_citations_size",
            "length(CAST(research_citations AS TEXT)) <= 65536",
        )
    _replace_outcome_constraint(f"{_OLD_OUTCOMES},{_RESEARCH_OUTCOMES}")
    capabilities = sa.table(
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
        capabilities,
        [
            {
                "id": uuid4(),
                "key": "web.research",
                "name": "Web research",
                "description": "Search and retrieve bounded public web evidence",
                "category": "research",
                "default_risk_level": 1,
                "allowed_actions": ["search", "fetch", "multi_source"],
                "external_side_effect": False,
                "financial": False,
                "data_destructive": False,
                "privacy_impact": True,
                "enabled": True,
            }
        ],
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM capabilities WHERE key = 'web.research'"))
    _replace_outcome_constraint(_OLD_OUTCOMES)
    with op.batch_alter_table("conversation_messages") as batch:
        batch.drop_constraint("ck_message_research_citations_size", type_="check")
        batch.drop_column("research_citations")
