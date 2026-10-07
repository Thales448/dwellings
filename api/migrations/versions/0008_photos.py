"""listing photo copies

Revision ID: 0008_photos
Revises: 0007_member_agents
Create Date: 2026-09-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_photos"
down_revision: str | None = "0007_member_agents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "photos",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("listing_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("original_url", sa.String(length=1000), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("phash", sa.String(length=16), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("caption", sa.String(length=200), nullable=True),
        sa.Column("is_cover", sa.Boolean(), nullable=False),
        sa.Column("shows_kitchen", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("listing_id", "sha256"),
    )
    op.create_index("ix_photos_listing_id", "photos", ["listing_id"])


def downgrade() -> None:
    op.drop_index("ix_photos_listing_id", table_name="photos")
    op.drop_table("photos")
