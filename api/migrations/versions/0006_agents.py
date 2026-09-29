"""agents, pairing codes, and comments

Revision ID: 0006_agents
Revises: 0005_listings
Create Date: 2026-09-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_agents"
down_revision: str | None = "0005_listings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("hunt_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_prefix", sa.String(length=8), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ip", sa.String(length=64), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["hunt_id"], ["hunts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_agents_hunt_id", "agents", ["hunt_id"])
    op.create_table(
        "pairing_codes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("hunt_id", sa.String(length=36), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["hunt_id"], ["hunts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("code_hash"),
    )
    op.create_index("ix_pairing_codes_hunt_id", "pairing_codes", ["hunt_id"])
    op.create_table(
        "comments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("listing_id", sa.String(length=36), nullable=False),
        sa.Column("author_user_id", sa.String(length=36), nullable=True),
        sa.Column("author_agent_id", sa.String(length=36), nullable=True),
        sa.Column("text", sa.String(length=2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_comments_listing_id", "comments", ["listing_id"])


def downgrade() -> None:
    op.drop_table("comments")
    op.drop_table("pairing_codes")
    op.drop_table("agents")
