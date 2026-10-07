from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Photo(Base):
    __tablename__ = "photos"
    __table_args__ = (UniqueConstraint("listing_id", "sha256"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    listing_id: Mapped[str] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    origin: Mapped[str] = mapped_column(String(16))
    original_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64))
    phash: Mapped[str] = mapped_column(String(16))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    caption: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_cover: Mapped[bool] = mapped_column(Boolean, default=False)
    shows_kitchen: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
