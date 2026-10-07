import secrets
from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select

from app.agents.auth import SCOPES, mac
from app.agents.models import Agent, PairingCode
from app.auth.models import LoginThrottle
from app.auth.service import _load_live_session
from app.core.clock import as_utc, utcnow
from app.core.config import get_settings
from app.core.db import session_scope
from app.core.request_ctx import current_authorization
from app.events.service import add_event
from app.listings.attrs import NycAttrs, TxAttrs
from app.listings.normalize import (
    ADDRESS_PRECISION,
    DEMOTION,
    HONESTY,
    LISTING_TYPES,
    SCAM,
    STATUSES,
    UNIT_KINDS,
)
from app.tenancy.models import Hunt
from app.tenancy.service import agent_allowlist, require_hunt

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
TOOLS = (
    "get_manifest",
    "post_listing",
    "post_listings_bulk",
    "update_listing",
    "set_status",
    "mark_checked",
    "list_listings",
    "get_listing",
    "add_comment",
)
Error = str


def _code() -> str:
    chunk = "".join(secrets.choice(ALPHABET) for _ in range(4))
    chunk_b = "".join(secrets.choice(ALPHABET) for _ in range(4))
    return f"DWL-{chunk}-{chunk_b}"


def _scopes(raw: object) -> list[str] | None:
    if raw is None:
        return list(SCOPES)
    if not isinstance(raw, list) or not raw:
        return None
    chosen = [str(item) for item in raw]
    if any(item not in SCOPES for item in chosen):
        return None
    return chosen


def _pair_locked(db: Any, ip: str) -> bool:
    row = db.get(LoginThrottle, f"pair:{ip}")
    if row is None or row.locked_until is None:
        return False
    return as_utc(row.locked_until) > utcnow()


def _pair_fail(db: Any, ip: str) -> None:
    subject = f"pair:{ip}"
    row = db.get(LoginThrottle, subject)
    if row is None:
        row = LoginThrottle(subject=subject, failures=0)
        db.add(row)
    row.failures = int(row.failures or 0) + 1
    if row.failures >= 5:
        row.locked_until = utcnow() + timedelta(minutes=10)


def _pair_clear(db: Any, ip: str) -> None:
    row = db.get(LoginThrottle, f"pair:{ip}")
    if row is not None:
        row.failures = 0
        row.locked_until = None


def create_pairing_code(
    token: str | None, ip: str, hunt_id: str, scopes: object
) -> dict[str, Any] | Error:
    chosen = _scopes(scopes)
    if chosen is None:
        return "invalid"
    with session_scope() as db:
        found = _load_live_session(db, token or "", ip) if token else None
        if found is None:
            return "unauthenticated"
        user, _row = found
        access = require_hunt(db, user.id, hunt_id, "owner")
        if isinstance(access, str):
            return access
        code = _code()
        expires_at = utcnow() + timedelta(minutes=10)
        db.add(
            PairingCode(
                code_hash=mac(code),
                hunt_id=hunt_id,
                scopes=chosen,
                created_by=user.id,
                expires_at=expires_at,
            )
        )
        add_event(
            db,
            type="agent.pairing_code",
            actor_type="user",
            actor_id=user.id,
            hunt_id=hunt_id,
            payload={"scopes": chosen},
        )
        return {"code": code, "expires_at": expires_at.isoformat(), "scopes": chosen}


def pair_agent(ip: str, code: str, name: str) -> dict[str, Any] | Error:
    label = name.strip()
    if not label or len(label) > 80 or not code.startswith("DWL-"):
        return "invalid"
    with session_scope() as db:
        if _pair_locked(db, ip):
            return "limited"
        row = db.scalar(select(PairingCode).where(PairingCode.code_hash == mac(code.strip())))
        now = utcnow()
        usable = (
            row is not None
            and row.used_at is None
            and row.attempts < 5
            and as_utc(row.expires_at) > now
        )
        if row is None or not usable:
            if row is not None:
                row.attempts = int(row.attempts or 0) + 1
            _pair_fail(db, ip)
            return "invalid"
        hunt = db.get(Hunt, row.hunt_id)
        if hunt is None:
            return "invalid"
        agent_id = str(uuid4())
        secret = secrets.token_urlsafe(32)
        raw = f"dwl_agent_{agent_id}_{secret}"
        agent = Agent(
            id=agent_id,
            hunt_id=hunt.id,
            name=label,
            token_hash=mac(raw),
            token_prefix=raw[:8],
            scopes=list(row.scopes),
            created_by=row.created_by,
            last_seen_at=now,
            last_ip=ip[:64],
        )
        db.add(agent)
        row.used_at = now
        row.agent_id = agent_id
        _pair_clear(db, ip)
        add_event(
            db,
            type="agent.paired",
            actor_type="agent",
            actor_id=agent_id,
            hunt_id=hunt.id,
            payload={"name": label},
        )
        base = get_settings().public_url.rstrip("/")
        return {
            "agent_id": agent_id,
            "token": raw,
            "hunt": {"id": hunt.id, "name": hunt.name, "slug": hunt.slug, "kind": hunt.kind},
            "scopes": list(row.scopes),
            "mcp_url": f"{base}/mcp",
            "manifest_url": f"{base}/api/v1/agent/manifest",
        }


def _require_agent(db: Any, ip: str) -> tuple[Agent, Hunt] | Error:
    from app.agents.auth import actor_from_bearer

    header = current_authorization()
    if not header:
        return "unauthenticated"
    actor = actor_from_bearer(db, header, ip)
    if actor is None or actor.kind != "agent" or actor.hunt_id is None:
        return "unauthenticated"
    agent = db.get(Agent, actor.id)
    hunt = db.get(Hunt, actor.hunt_id)
    if agent is None or hunt is None:
        return "unauthenticated"
    return agent, hunt


def manifest(ip: str) -> dict[str, Any] | Error:
    with session_scope() as db:
        found = _require_agent(db, ip)
        if isinstance(found, str):
            return found
        _agent, hunt = found
        schema = NycAttrs.model_json_schema() if hunt.schema_id == "nyc-rental-v1" else {}
        if hunt.schema_id == "tx-purchase-v1":
            schema = TxAttrs.model_json_schema()
        return {
            "hunt": {
                "id": hunt.id,
                "name": hunt.name,
                "slug": hunt.slug,
                "kind": hunt.kind,
                "schema": hunt.schema_id,
            },
            "criteria": hunt.criteria,
            "attrs_schema": schema,
            "enums": {
                "status": sorted(STATUSES),
                "listing_type": sorted(LISTING_TYPES),
                "unit_kind": sorted(UNIT_KINDS),
                "address_precision": sorted(ADDRESS_PRECISION),
                "honesty_flags": sorted(HONESTY),
                "demotion_reason": sorted(DEMOTION),
                "scam_risk": sorted(SCAM),
            },
            "title_guide": {
                "max_characters": 140,
                "rules": [
                    "Use the Craigslist posting title.",
                    "Use the Craigslist posting description as notes, the same words.",
                    "Use the posting link, not a search page.",
                ],
                "examples": [
                    "https://newyork.craigslist.org/que/apa/d/sunnyside-bright-1br/1234567890.html"
                ],
            },
            "rules": {
                "never_delete": (
                    "Never delete a listing. DELETE sets status dead and keeps the row. "
                    "Hard delete is admin-only with ?hard=true."
                ),
                "photos": (
                    "Send photos as [{url, caption, shows_kitchen}] on each listing. "
                    "The server copies them and keeps the copies after the listing is dead. "
                    "Send the real gallery, not a generated picture and not only the page preview. "
                    "If you send none, the server tries the page's preview image."
                ),
                "description_verified_ready": (
                    "notes is the Craigslist posting description, copied as written. "
                    "address, lat, and lng are required so the deck can show a map. "
                    "attrs.verified is true only after you have checked the listing yourself. "
                    "attrs.ready is true only when the description, address, "
                    "map point, and photos are present."
                ),
                "craigslist": (
                    "For nyc-rental-v1 the url must be one Craigslist posting, "
                    "https://{city}.craigslist.org/{area}/{apa|abo}/d/{slug}/{id}.html. "
                    "The server fetches that page. The listing stays hidden until the link "
                    "opens, the post is still up, the title matches the posting title, "
                    "and notes matches the posting description."
                ),
                "presentable": (
                    "For nyc-rental-v1, a listing is presentable only when that Craigslist "
                    "check passed, status is new, alive, or watching, listing_type is couple, "
                    "unit_kind is full_studio or full_1br (price ≤ criteria.price_ceiling, "
                    "Roosevelt Island may stretch to criteria.ri_price_ceiling for those kinds "
                    "only) or full_2br_plus (price ≤ criteria.price_ceiling_2br; the RI stretch "
                    "does not apply to 2BRs), it is not demoted, scam_risk is not high, "
                    "unavailable_date is empty, and geo_bucket is not out_of_scope."
                ),
            },
            "rate_limits": {"pairing_attempts": 5, "bulk_max": 200},
            "endpoints": [
                "GET /api/v1/agent/manifest",
                "POST /api/v1/agent/heartbeat",
                "POST /api/v1/agent/rotate-token",
                "POST /api/v1/listings",
                "POST /api/v1/listings/bulk",
                "PATCH /api/v1/listings/{id}",
                "POST /api/v1/listings/{id}/status",
                "POST /api/v1/listings/{id}/checked",
                "DELETE /api/v1/listings/{id}",
                "GET /api/v1/listings",
                "GET /api/v1/listings/{id}",
                "POST /api/v1/listings/{id}/comments",
            ],
            "tools": list(TOOLS),
        }


def heartbeat(ip: str, body: dict[str, Any]) -> dict[str, Any] | Error:
    with session_scope() as db:
        found = _require_agent(db, ip)
        if isinstance(found, str):
            return found
        agent, _hunt = found
        agent.last_seen_at = utcnow()
        agent.last_ip = ip[:64]
        return {
            "status": str(body.get("status") or "ok"),
            "version": body.get("version"),
            "next_run_at": body.get("next_run_at"),
            "agent_id": agent.id,
            "server_time": iso_utc(utcnow()),
        }


def rotate_token(ip: str) -> dict[str, Any] | Error:
    with session_scope() as db:
        found = _require_agent(db, ip)
        if isinstance(found, str):
            return found
        agent, _hunt = found
        secret = secrets.token_urlsafe(32)
        raw = f"dwl_agent_{agent.id}_{secret}"
        agent.token_hash = mac(raw)
        agent.token_prefix = raw[:8]
        add_event(
            db,
            type="agent.token_rotated",
            actor_type="agent",
            actor_id=agent.id,
            hunt_id=agent.hunt_id,
            payload={},
        )
        return {"token": raw, "token_prefix": raw[:8]}


def list_agents(token: str | None, ip: str, hunt_id: str) -> list[dict[str, Any]] | Error:
    with session_scope() as db:
        found = _load_live_session(db, token or "", ip) if token else None
        if found is None:
            return "unauthenticated"
        user, _row = found
        access = require_hunt(db, user.id, hunt_id, "viewer")
        if isinstance(access, str):
            return access
        from app.listings.models import Listing

        rows = db.scalars(select(Agent).where(Agent.hunt_id == hunt_id)).all()
        allowed = agent_allowlist(db, user.id, hunt_id, is_admin=user.is_admin)
        public: list[dict[str, Any]] = []
        for agent in rows:
            if allowed is not None and agent.id not in allowed:
                continue
            count = db.scalar(
                select(func.count())
                .select_from(Listing)
                .where(Listing.created_by_agent == agent.id)
            )
            public.append(
                {
                    "id": agent.id,
                    "name": agent.name,
                    "scopes": list(agent.scopes),
                    "token_prefix": agent.token_prefix,
                    "last_seen_at": iso_utc(agent.last_seen_at),
                    "revoked_at": iso_utc(agent.revoked_at),
                    "posts": int(count or 0),
                }
            )
        return public


def revoke_agent(
    token: str | None, ip: str, hunt_id: str, agent_id: str
) -> dict[str, Any] | Error:
    with session_scope() as db:
        found = _load_live_session(db, token or "", ip) if token else None
        if found is None:
            return "unauthenticated"
        user, _row = found
        access = require_hunt(db, user.id, hunt_id, "owner")
        if isinstance(access, str):
            return access
        agent = db.get(Agent, agent_id)
        if agent is None or agent.hunt_id != hunt_id:
            return "missing"
        agent.revoked_at = utcnow()
        add_event(
            db,
            type="agent.revoked",
            actor_type="user",
            actor_id=user.id,
            hunt_id=hunt_id,
            payload={"agent_id": agent_id},
        )
        return {"ok": True}
