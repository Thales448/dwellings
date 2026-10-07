"""per-person listing ratings

Revision ID: 0009_ratings
Revises: 0008_photos
Create Date: 2026-09-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_ratings"
down_revision: str | None = "0008_photos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ratings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("listing_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("stars", sa.Integer(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("listing_id", "user_id", name="uq_ratings_listing_user"),
    )
    op.create_index("ix_ratings_listing_id", "ratings", ["listing_id"])
    op.create_index("ix_ratings_user_id", "ratings", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_ratings_user_id", table_name="ratings")
    op.drop_index("ix_ratings_listing_id", table_name="ratings")
    op.drop_table("ratings")
