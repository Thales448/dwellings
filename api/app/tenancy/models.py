from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.core.db import Base


class Hunt(Base):
    __tablename__ = "hunts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16))
    schema_id: Mapped[str] = mapped_column("schema", String(64))
    criteria: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rating_scale: Mapped[int] = mapped_column(Integer, default=5)
    rating_weights: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HuntMember(Base):
    __tablename__ = "hunt_members"

    hunt_id: Mapped[str] = mapped_column(
        ForeignKey("hunts.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(16))
    rater_label: Mapped[str] = mapped_column(String(80))
    agents_restricted: Mapped[bool] = mapped_column(Boolean, default=False)


class MemberAgentGrant(Base):
    __tablename__ = "member_agent_grants"

    hunt_id: Mapped[str] = mapped_column(
        ForeignKey("hunts.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
