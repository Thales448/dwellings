from datetime import date, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.core.db import Base


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("hunt_id", "short_id", name="uq_listings_hunt_short"),
        UniqueConstraint("hunt_id", "external_id", name="uq_listings_hunt_external"),
        UniqueConstraint("hunt_id", "url", name="uq_listings_hunt_url"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    hunt_id: Mapped[str] = mapped_column(ForeignKey("hunts.id", ondelete="CASCADE"), index=True)
    short_id: Mapped[int] = mapped_column(Integer)
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    url: Mapped[str] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(40), default="unknown")
    title: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    unavailable_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    availability_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    listing_type: Mapped[str] = mapped_column(String(16), default="couple")
    unit_kind: Mapped[str] = mapped_column(String(20), default="unknown")
    beds: Mapped[float | None] = mapped_column(Float, nullable=True)
    beds_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    baths: Mapped[float | None] = mapped_column(Float, nullable=True)
    price: Mapped[float] = mapped_column(Float)
    price_per_person: Mapped[float | None] = mapped_column(Float, nullable=True)
    address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address_precision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(String(80), nullable=True)
    borough_or_city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    geo_bucket: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    hunt_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fit_reasons: Mapped[list[Any]] = mapped_column(JSON, default=list)
    honesty_flags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    demoted: Mapped[bool] = mapped_column(Boolean, default=False)
    demotion_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    scam_risk_agent: Mapped[str | None] = mapped_column(String(16), nullable=True)
    scam_notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scam_risk: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_presentable: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    source_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    days_on_market: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attrs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by_agent: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
