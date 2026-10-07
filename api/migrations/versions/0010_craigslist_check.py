"""craigslist link check

Revision ID: 0010_craigslist_check
Revises: 0009_ratings
Create Date: 2026-09-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_craigslist_check"
down_revision: str | None = "0009_ratings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("listings") as batch:
        batch.alter_column(
            "title",
            existing_type=sa.String(length=60),
            type_=sa.String(length=140),
            existing_nullable=False,
        )
        batch.add_column(
            sa.Column("link_ok", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("link_error", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("link_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE listings SET is_presentable = 0 "
        "WHERE hunt_id IN (SELECT id FROM hunts WHERE \"schema\" = 'nyc-rental-v1')"
    )


def downgrade() -> None:
    with op.batch_alter_table("listings") as batch:
        batch.drop_column("link_checked_at")
        batch.drop_column("link_error")
        batch.drop_column("link_ok")
        batch.alter_column(
            "title",
            existing_type=sa.String(length=140),
            type_=sa.String(length=60),
            existing_nullable=False,
        )
