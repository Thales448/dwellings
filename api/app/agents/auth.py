from __future__ import annotations

import hashlib
import hmac
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.listings.service import Actor

from app.agents.models import Agent
from app.core.clock import utcnow
from app.core.config import get_settings

SCOPES = (
    "listings:write",
    "listings:read",
    "ratings:read",
    "learn:read",
    "digests:write",
)


def mac(value: str) -> str:
    pepper = get_settings().token_pepper.encode()
    return hmac.new(pepper, value.encode(), hashlib.sha256).hexdigest()


def actor_from_bearer(db: Session, header: str, ip: str) -> Actor | None:
    from app.listings.service import Actor

    if not header.lower().startswith("bearer "):
        return None
    raw = header.split(" ", 1)[1].strip()
    prefix = "dwl_agent_"
    if not raw.startswith(prefix) or len(raw) < len(prefix) + 37:
        return None
    body = raw[len(prefix) :]
    agent_id = body[:36]
    if body[36] != "_":
        return None
    agent = db.get(Agent, agent_id)
    if agent is None or agent.revoked_at is not None:
        return None
    if not hmac.compare_digest(agent.token_hash, mac(raw)):
        return None
    agent.last_seen_at = utcnow()
    agent.last_ip = ip[:64]
    scopes = frozenset(str(item) for item in agent.scopes)
    return Actor(
        kind="agent",
        id=agent.id,
        is_admin=False,
        hunt_id=agent.hunt_id,
        scopes=scopes,
    )
