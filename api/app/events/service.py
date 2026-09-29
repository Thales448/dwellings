from typing import Any

from sqlalchemy.orm import Session

from app.events.models import Event


def add_event(
    session: Session,
    *,
    type: str,
    actor_type: str,
    actor_id: str | None,
    payload: dict[str, Any] | None = None,
    hunt_id: str | None = None,
    listing_id: str | None = None,
) -> None:
    session.add(
        Event(
            hunt_id=hunt_id,
            listing_id=listing_id,
            type=type,
            actor_type=actor_type,
            actor_id=actor_id,
            payload=payload or {},
        )
    )
