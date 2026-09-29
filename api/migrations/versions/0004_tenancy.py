"""hunts and memberships

Revision ID: 0004_tenancy
Revises: 0003_passkeys
Create Date: 2026-09-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_tenancy"
down_revision: str | None = "0003_passkeys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hunts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("schema", sa.String(length=64), nullable=False),
        sa.Column("criteria", sa.JSON(), nullable=False),
        sa.Column("rating_scale", sa.Integer(), nullable=False),
        sa.Column("rating_weights", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "hunt_members",
        sa.Column("hunt_id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), primary_key=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("rater_label", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(["hunt_id"], ["hunts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("hunt_members")
    op.drop_table("hunts")
