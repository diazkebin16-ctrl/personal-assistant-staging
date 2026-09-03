"""Make each capability the authority for its valid action vocabulary.

Revision ID: 0003_capability_actions
Revises: 0002_permissions_risk_audit
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_capability_actions"
down_revision: str | None = "0002_permissions_risk_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ALLOWED_ACTIONS: dict[str, list[str]] = {
    "device.read": ["read"],
    "device.manage": ["register", "revoke", "update"],
    "notification.send": ["send"],
    "data.delete": ["delete"],
    "finance.read": ["read"],
    "finance.execute": [
        "buy",
        "cancel_order",
        "change_leverage",
        "deposit",
        "execute",
        "increase_risk",
        "place_order",
        "sell",
        "transfer",
        "withdraw",
    ],
}


def upgrade() -> None:
    """Add and populate the server-owned action vocabulary without losing data."""
    op.add_column("capabilities", sa.Column("allowed_actions", sa.JSON(), nullable=True))

    capability = sa.table(
        "capabilities",
        sa.column("key", sa.String()),
        sa.column("allowed_actions", sa.JSON()),
    )
    connection = op.get_bind()
    connection.execute(sa.update(capability).values(allowed_actions=[]))
    for key, actions in _ALLOWED_ACTIONS.items():
        connection.execute(
            sa.update(capability).where(capability.c.key == key).values(allowed_actions=actions)
        )

    with op.batch_alter_table("capabilities") as batch_op:
        batch_op.alter_column("allowed_actions", existing_type=sa.JSON(), nullable=False)
        batch_op.create_check_constraint(
            "ck_capabilities_allowed_actions_size",
            "length(CAST(allowed_actions AS TEXT)) <= 4096",
        )


def downgrade() -> None:
    """Remove only the action vocabulary column added by this correction."""
    with op.batch_alter_table("capabilities") as batch_op:
        batch_op.drop_constraint("ck_capabilities_allowed_actions_size", type_="check")
        batch_op.drop_column("allowed_actions")
