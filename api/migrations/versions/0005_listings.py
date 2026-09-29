"""listings and jobs

Revision ID: 0005_listings
Revises: 0004_tenancy
Create Date: 2026-09-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_listings"
down_revision: str | None = "0004_tenancy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "listings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("hunt_id", sa.String(length=36), nullable=False),
        sa.Column("short_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=120), nullable=True),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unavailable_date", sa.Date(), nullable=True),
        sa.Column("availability_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("listing_type", sa.String(length=16), nullable=False),
        sa.Column("unit_kind", sa.String(length=20), nullable=False),
        sa.Column("beds", sa.Float(), nullable=True),
        sa.Column("beds_label", sa.String(length=20), nullable=True),
        sa.Column("baths", sa.Float(), nullable=True),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("price_per_person", sa.Float(), nullable=True),
        sa.Column("address", sa.String(length=200), nullable=True),
        sa.Column("address_precision", sa.String(length=16), nullable=True),
        sa.Column("neighborhood", sa.String(length=80), nullable=True),
        sa.Column("borough_or_city", sa.String(length=80), nullable=True),
        sa.Column("geo_bucket", sa.String(length=40), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("hunt_score", sa.Float(), nullable=True),
        sa.Column("fit_reasons", sa.JSON(), nullable=False),
        sa.Column("honesty_flags", sa.JSON(), nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("demoted", sa.Boolean(), nullable=False),
        sa.Column("demotion_reason", sa.String(length=40), nullable=True),
        sa.Column("scam_risk_agent", sa.String(length=16), nullable=True),
        sa.Column("scam_notes", sa.String(length=500), nullable=True),
        sa.Column("scam_risk", sa.String(length=16), nullable=True),
        sa.Column("is_presentable", sa.Boolean(), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("days_on_market", sa.Integer(), nullable=True),
        sa.Column("attrs", sa.JSON(), nullable=False),
        sa.Column("created_by_agent", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["hunt_id"], ["hunts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("hunt_id", "short_id", name="uq_listings_hunt_short"),
        sa.UniqueConstraint("hunt_id", "external_id", name="uq_listings_hunt_external"),
        sa.UniqueConstraint("hunt_id", "url", name="uq_listings_hunt_url"),
    )
    op.create_index("ix_listings_hunt_id", "listings", ["hunt_id"])
    op.create_index("ix_listings_status", "listings", ["status"])
    op.create_index("ix_listings_is_presentable", "listings", ["is_presentable"])
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_jobs_kind", "jobs", ["kind"])
    op.create_index("ix_jobs_run_after", "jobs", ["run_after"])


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("listings")
