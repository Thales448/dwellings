"""per-member agent visibility

Revision ID: 0007_member_agents
Revises: 0006_agents
Create Date: 2026-09-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_member_agents"
down_revision: str | None = "0006_agents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "hunt_members",
        sa.Column("agents_restricted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "member_agent_grants",
        sa.Column("hunt_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hunt_id"], ["hunts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("hunt_id", "user_id", "agent_id"),
    )


def downgrade() -> None:
    op.drop_table("member_agent_grants")
    op.drop_column("hunt_members", "agents_restricted")
