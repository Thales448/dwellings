import base64
import json
import queue
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.orm import Session

from app.auth.service import _load_live_session
from app.core.clock import utcnow
from app.core.db import session_scope
from app.core.request_ctx import current_authorization
from app.events.models import Event
from app.events.service import add_event
from app.jobs.models import Job
from app.listings.attrs import validate_attrs
from app.listings.craigslist import NOTES_MAX, TITLE_MAX
from app.listings.models import Comment, Listing, Rating
from app.listings.normalize import (
    ACTIVE,
    ADDRESS_PRECISION,
    DEMOTION,
    HONESTY,
    LISTING_TYPES,
    SCAM,
    STATUSES,
    UNIT_KINDS,
    normalize_beds,
    normalize_url,
)
from app.listings.presentable import presentable
from app.listings.stream import hub
from app.photos.present import photos_by_listing
from app.tenancy.models import Hunt, HuntMember
from app.tenancy.service import agent_allowlist, require_hunt

Error = str
SORTS = {"hunt_score", "predicted", "combined", "newest", "price"}


@dataclass
class Actor:
    kind: str
    id: str
    is_admin: bool
    hunt_id: str | None = None
    scopes: frozenset[str] = frozenset()


def _actor(
    db: Session, token: str | None, ip: str, authorization: str | None = None
) -> Actor | None:
    header = authorization if authorization is not None else current_authorization()
    if header:
        from app.agents.auth import actor_from_bearer

        return actor_from_bearer(db, header, ip)
    if not token:
        return None
    found = _load_live_session(db, token, ip)
    if found is None:
        return None
    user, _row = found
    return Actor(kind="user", id=user.id, is_admin=user.is_admin)


def _open_hunt(db: Session, actor: Actor, hunt_id: str, role: str, scope: str) -> Hunt | Error:
    if actor.kind == "agent":
        if actor.hunt_id != hunt_id:
            return "missing"
        if scope not in actor.scopes:
            return "forbidden"
        hunt = db.get(Hunt, hunt_id)
        return hunt if hunt is not None else "missing"
    access = require_hunt(db, actor.id, hunt_id, role)
    if isinstance(access, str):
        return access
    hunt, _member = access
    return hunt


def _listing_visible(db: Session, actor: Actor, row: Listing) -> bool:
    if actor.kind != "user":
        return True
    allowed = agent_allowlist(db, actor.id, row.hunt_id, is_admin=actor.is_admin)
    if allowed is None or row.created_by_agent is None:
        return True
    return row.created_by_agent in allowed


def _public(row: Listing, photos: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "id": row.id,
        "hunt_id": row.hunt_id,
        "short_id": row.short_id,
        "external_id": row.external_id,
        "url": row.url,
        "source": row.source,
        "title": row.title,
        "status": row.status,
        "first_seen": row.first_seen.isoformat(),
        "last_seen": row.last_seen.isoformat(),
        "unavailable_date": row.unavailable_date.isoformat() if row.unavailable_date else None,
        "availability_checked_at": (
            row.availability_checked_at.isoformat() if row.availability_checked_at else None
        ),
        "listing_type": row.listing_type,
        "unit_kind": row.unit_kind,
        "beds": row.beds,
        "beds_label": row.beds_label,
        "baths": row.baths,
        "price": row.price,
        "price_per_person": row.price_per_person,
        "address": row.address,
        "address_precision": row.address_precision,
        "neighborhood": row.neighborhood,
        "borough_or_city": row.borough_or_city,
        "geo_bucket": row.geo_bucket,
        "lat": row.lat,
        "lng": row.lng,
        "hunt_score": row.hunt_score,
        "fit_reasons": row.fit_reasons,
        "honesty_flags": row.honesty_flags,
        "notes": row.notes,
        "demoted": row.demoted,
        "demotion_reason": row.demotion_reason,
        "scam_risk_agent": row.scam_risk_agent,
        "scam_notes": row.scam_notes,
        "scam_risk": row.scam_risk,
        "is_presentable": row.is_presentable,
        "presentable": row.is_presentable,
        "link_check": {
            "ok": bool(row.link_ok),
            "error": row.link_error,
            "checked_at": row.link_checked_at.isoformat() if row.link_checked_at else None,
        },
        "source_snapshot": row.source_snapshot,
        "days_on_market": row.days_on_market,
        "attrs": row.attrs,
        "created_by_agent": row.created_by_agent,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "photos": photos or [],
        "ratings": [],
        "my_rating": None,
        "comments": [],
        "events": [],
    }


def _rating_public(row: Rating | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {"stars": row.stars, "passed": row.passed}


def _ratings_for(db: Session, user_id: str, listing_ids: list[str]) -> dict[str, Rating]:
    if not listing_ids:
        return {}
    rows = db.scalars(
        select(Rating).where(Rating.user_id == user_id, Rating.listing_id.in_(listing_ids))
    ).all()
    return {row.listing_id: row for row in rows}


def _stamp_ratings(
    db: Session, actor: Actor, rows: list[Listing], bodies: list[dict[str, Any]]
) -> None:
    if actor.kind != "user":
        return
    found = _ratings_for(db, actor.id, [row.id for row in rows])
    for row, body in zip(rows, bodies, strict=True):
        body["my_rating"] = _rating_public(found.get(row.id))


def _detail(db: Session, row: Listing) -> dict[str, Any]:
    body = _public(row, photos_by_listing(db, [row.id]).get(row.id, []))
    events = db.scalars(
        select(Event).where(Event.listing_id == row.id).order_by(Event.at.desc()).limit(50)
    ).all()
    body["events"] = [
        {
            "id": event.id,
            "type": event.type,
            "actor_type": event.actor_type,
            "actor_id": event.actor_id,
            "payload": event.payload,
            "at": event.at.isoformat(),
        }
        for event in events
    ]
    notes = db.scalars(
        select(Comment).where(Comment.listing_id == row.id).order_by(Comment.created_at.asc())
    ).all()
    body["comments"] = [
        {
            "id": note.id,
            "text": note.text,
            "author_type": "agent" if note.author_agent_id else "user",
            "author_user_id": note.author_user_id,
            "author_agent_id": note.author_agent_id,
            "created_at": note.created_at.isoformat(),
        }
        for note in notes
    ]
    return body


def _reset_link(row: Listing, hunt: Hunt) -> None:
    if hunt.schema_id != "nyc-rental-v1":
        return
    row.link_ok = False
    row.link_error = None
    row.link_checked_at = None
    snap = dict(row.source_snapshot or {})
    snap.setdefault("title", row.title)
    snap.setdefault("price", row.price)
    snap["craigslist"] = {"ok": False, "error": "not checked yet"}
    row.source_snapshot = snap


def _enqueue(db: Session, kind: str, payload: dict[str, Any]) -> None:
    db.add(Job(kind=kind, payload=payload, run_after=utcnow()))


def _publish(event: dict[str, Any] | None) -> None:
    if event is not None:
        hub.publish(event)


def _apply_status(row: Listing, status: str, reason: str | None) -> str | None:
    if status not in STATUSES:
        return "invalid"
    if status == "demoted":
        if reason not in DEMOTION:
            return "invalid"
        row.demoted = True
        row.demotion_reason = reason
    elif status in ACTIVE:
        row.demoted = False
        row.demotion_reason = None
        row.unavailable_date = None
    if status in {"dead", "rented"} and row.unavailable_date is None:
        row.unavailable_date = utcnow().date()
    row.status = status
    return None


def _assign(row: Listing, body: dict[str, Any], *, creating: bool) -> str | None:
    if "title" in body or creating:
        title = str(body.get("title", row.title if not creating else "")).strip()
        if not title or len(title) > TITLE_MAX:
            return "invalid"
        row.title = title
    if "price" in body or creating:
        try:
            row.price = float(body["price"])
        except (KeyError, TypeError, ValueError):
            return "invalid"
    if "beds" in body and body["beds"] is not None:
        beds = normalize_beds(body["beds"])
        if beds is None:
            return "invalid"
        row.beds, row.beds_label = beds
    if body.get("beds_label"):
        row.beds_label = str(body["beds_label"])[:20]
    for key, kind in (
        ("listing_type", LISTING_TYPES),
        ("unit_kind", UNIT_KINDS),
        ("address_precision", ADDRESS_PRECISION),
    ):
        if key in body and body[key] is not None:
            if body[key] not in kind:
                return "invalid"
            setattr(row, key, body[key])
    if "honesty_flags" in body and body["honesty_flags"] is not None:
        flags = body["honesty_flags"]
        if not isinstance(flags, list) or any(flag not in HONESTY for flag in flags):
            return "invalid"
        row.honesty_flags = flags
    if "fit_reasons" in body and body["fit_reasons"] is not None:
        reasons = body["fit_reasons"]
        if not isinstance(reasons, list) or len(reasons) > 5:
            return "invalid"
        row.fit_reasons = [str(item)[:80] for item in reasons]
    if "scam_risk_agent" in body:
        risk = body["scam_risk_agent"]
        if risk is not None and risk not in SCAM:
            return "invalid"
        row.scam_risk_agent = risk
        row.scam_risk = risk
    for key in (
        "source",
        "neighborhood",
        "borough_or_city",
        "geo_bucket",
        "scam_notes",
        "address",
        "external_id",
    ):
        if key in body and body[key] is not None:
            setattr(row, key, str(body[key])[:200])
    if "notes" in body and body["notes"] is not None:
        row.notes = str(body["notes"])[:NOTES_MAX]
    for key in ("baths", "price_per_person", "lat", "lng", "hunt_score"):
        if key in body and body[key] is not None:
            try:
                setattr(row, key, float(body[key]))
            except (TypeError, ValueError):
                return "invalid"
    if row.hunt_score is not None and not 0 <= row.hunt_score <= 10:
        return "invalid"
    if "days_on_market" in body and body["days_on_market"] is not None:
        try:
            row.days_on_market = int(body["days_on_market"])
        except (TypeError, ValueError):
            return "invalid"
    if "status" in body and body["status"] is not None:
        reason = body.get("demotion_reason") or body.get("reason")
        if _apply_status(row, str(body["status"]), None if reason is None else str(reason)):
            return "invalid"
    return None


def _next_short_id(db: Session, hunt_id: str) -> int:
    current = db.scalar(select(func.max(Listing.short_id)).where(Listing.hunt_id == hunt_id))
    return int(current or 0) + 1


def _find(db: Session, hunt_id: str, external_id: str | None, url: str) -> Listing | None:
    if external_id:
        found = db.scalar(
            select(Listing).where(Listing.hunt_id == hunt_id, Listing.external_id == external_id)
        )
        if found is not None:
            return found
    return db.scalar(select(Listing).where(Listing.hunt_id == hunt_id, Listing.url == url))


class _RowError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code


def _write_one(
    db: Session,
    actor: Actor,
    hunt_id: str,
    body: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]] | Error:
    try:
        with db.begin_nested():
            outcome = _write_saved(db, actor, hunt_id, body)
            if isinstance(outcome, str):
                raise _RowError(outcome)
            return outcome
    except _RowError as exc:
        return exc.code


def _write_saved(
    db: Session,
    actor: Actor,
    hunt_id: str,
    body: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]] | Error:
    hunt = _open_hunt(db, actor, hunt_id, "owner", "listings:write")
    if isinstance(hunt, str):
        return hunt
    url = normalize_url(body.get("url"))
    if url is None:
        return "invalid"
    external_id = body.get("external_id")
    external = str(external_id)[:120] if external_id else None
    attrs = validate_attrs(hunt.schema_id, body.get("attrs") or {})
    if isinstance(attrs, str):
        return attrs
    existing = _find(db, hunt.id, external, url)
    created = existing is None
    now = utcnow()
    if existing is None:
        row = Listing(
            hunt_id=hunt.id,
            short_id=_next_short_id(db, hunt.id),
            url=url,
            external_id=external,
            source_snapshot={},
            first_seen=now,
            last_seen=now,
            created_at=now,
            updated_at=now,
        )
        if _assign(row, body, creating=True):
            return "invalid"
        row.status = row.status or "new"
        row.listing_type = row.listing_type or "couple"
        row.unit_kind = row.unit_kind or "unknown"
        row.demoted = bool(row.demoted)
        row.attrs = attrs
        row.source_snapshot = {"title": row.title, "price": row.price}
        _reset_link(row, hunt)
        if actor.kind == "agent":
            row.created_by_agent = actor.id
        row.is_presentable = presentable(hunt, row)
        db.add(row)
        db.flush()
        event_type = "listing.created"
    else:
        row = existing
        previous_price = row.price
        if url != row.url:
            clash = db.scalar(
                select(Listing).where(
                    Listing.hunt_id == hunt.id, Listing.url == url, Listing.id != row.id
                )
            )
            if clash is not None:
                return "conflict"
            row.url = url
        if external and row.external_id and external != row.external_id:
            return "conflict"
        if external:
            row.external_id = external
        if _assign(row, body, creating=False):
            return "invalid"
        if "attrs" in body:
            row.attrs = attrs
        row.last_seen = now
        row.updated_at = now
        _reset_link(row, hunt)
        row.is_presentable = presentable(hunt, row)
        db.flush()
        event_type = "listing.updated"
        if previous_price != row.price:
            add_event(
                db,
                type="listing.price",
                actor_type=actor.kind,
                actor_id=actor.id,
                hunt_id=hunt.id,
                listing_id=row.id,
                payload={"from": previous_price, "to": row.price},
            )
            _enqueue(
                db,
                "bait_drift",
                {"listing_id": row.id, "hunt_id": hunt.id, "from": previous_price, "to": row.price},
            )
    photos = body.get("photos") or []
    if photos and not isinstance(photos, list):
        return "invalid"
    _enqueue(db, "photo", {"listing_id": row.id, "hunt_id": hunt.id, "photos": photos})
    _enqueue(db, "scam", {"listing_id": row.id, "hunt_id": hunt.id})
    if hunt.schema_id == "nyc-rental-v1":
        _enqueue(db, "verify", {"listing_id": row.id, "hunt_id": hunt.id})
    add_event(
        db,
        type=event_type,
        actor_type=actor.kind,
        actor_id=actor.id,
        hunt_id=hunt.id,
        listing_id=row.id,
        payload={"short_id": row.short_id, "status": row.status},
    )
    published = {
        "type": event_type,
        "hunt_id": hunt.id,
        "listing_id": row.id,
        "short_id": row.short_id,
        "status": row.status,
    }
    return {"listing": _public(row), "duplicate": not created, "created": created}, published


def upsert_listing(token: str | None, ip: str, body: dict[str, Any]) -> dict[str, Any] | Error:
    published: dict[str, Any] | None = None
    with session_scope() as db:
        actor = _actor(db, token, ip)
        if actor is None:
            return "unauthenticated"
        hunt_id = str(body.get("hunt_id") or actor.hunt_id or "")
        result = _write_one(db, actor, hunt_id, body)
        if isinstance(result, str):
            return result
        payload, published = result
    _publish(published)
    return payload


def bulk_listings(token: str | None, ip: str, body: dict[str, Any]) -> dict[str, Any] | Error:
    rows = body.get("listings")
    if not isinstance(rows, list) or len(rows) > 200:
        return "invalid"
    published: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    with session_scope() as db:
        actor = _actor(db, token, ip)
        if actor is None:
            return "unauthenticated"
        hunt_id = str(body.get("hunt_id") or actor.hunt_id or "")
        opened = _open_hunt(db, actor, hunt_id, "owner", "listings:write")
        if isinstance(opened, str):
            return opened
        for index, item in enumerate(rows):
            if not isinstance(item, dict):
                results.append({"index": index, "ok": False, "error": "invalid"})
                continue
            item = {**item, "hunt_id": hunt_id}
            outcome = _write_one(db, actor, hunt_id, item)
            if isinstance(outcome, str):
                results.append({"index": index, "ok": False, "error": outcome})
                continue
            payload, event = outcome
            published.append(event)
            results.append(
                {
                    "index": index,
                    "ok": True,
                    "status": 201 if payload["created"] else 200,
                    "duplicate": payload["duplicate"],
                    "id": payload["listing"]["id"],
                    "short_id": payload["listing"]["short_id"],
                }
            )
    for event in published:
        _publish(event)
    return {"results": results}


def patch_listing(
    token: str | None, ip: str, listing_id: str, body: dict[str, Any]
) -> dict[str, Any] | Error:
    published: dict[str, Any] | None = None
    with session_scope() as db:
        actor = _actor(db, token, ip)
        if actor is None:
            return "unauthenticated"
        row = db.get(Listing, listing_id)
        if row is None:
            return "missing"
        hunt = _open_hunt(db, actor, row.hunt_id, "owner", "listings:write")
        if isinstance(hunt, str):
            return hunt
        previous = row.price
        if "url" in body:
            url = normalize_url(body["url"])
            if url is None:
                return "invalid"
            clash = db.scalar(
                select(Listing).where(
                    Listing.hunt_id == hunt.id, Listing.url == url, Listing.id != row.id
                )
            )
            if clash is not None:
                return "conflict"
            row.url = url
        if "attrs" in body:
            attrs = validate_attrs(hunt.schema_id, body.get("attrs") or {})
            if isinstance(attrs, str):
                db.rollback()
                return attrs
            row.attrs = attrs
        if _assign(row, body, creating=False):
            db.rollback()
            return "invalid"
        row.updated_at = utcnow()
        _reset_link(row, hunt)
        row.is_presentable = presentable(hunt, row)
        if hunt.schema_id == "nyc-rental-v1":
            _enqueue(db, "verify", {"listing_id": row.id, "hunt_id": hunt.id})
        if previous != row.price:
            add_event(
                db,
                type="listing.price",
                actor_type=actor.kind,
                actor_id=actor.id,
                hunt_id=hunt.id,
                listing_id=row.id,
                payload={"from": previous, "to": row.price},
            )
            _enqueue(
                db,
                "bait_drift",
                {"listing_id": row.id, "from": previous, "to": row.price},
            )
        add_event(
            db,
            type="listing.updated",
            actor_type=actor.kind,
            actor_id=actor.id,
            hunt_id=hunt.id,
            listing_id=row.id,
            payload={"status": row.status},
        )
        published = {
            "type": "listing.updated",
            "hunt_id": hunt.id,
            "listing_id": row.id,
            "short_id": row.short_id,
            "status": row.status,
        }
        payload = {"listing": _public(row)}
    _publish(published)
    return payload


def set_status(
    token: str | None, ip: str, listing_id: str, status: str, reason: str | None
) -> dict[str, Any] | Error:
    published: dict[str, Any] | None = None
    with session_scope() as db:
        actor = _actor(db, token, ip)
        if actor is None:
            return "unauthenticated"
        row = db.get(Listing, listing_id)
        if row is None:
            return "missing"
        hunt = _open_hunt(db, actor, row.hunt_id, "owner", "listings:write")
        if isinstance(hunt, str):
            return hunt
        if _apply_status(row, status, reason):
            return "invalid"
        row.updated_at = utcnow()
        row.is_presentable = presentable(hunt, row)
        add_event(
            db,
            type="listing.status",
            actor_type=actor.kind,
            actor_id=actor.id,
            hunt_id=hunt.id,
            listing_id=row.id,
            payload={"status": row.status, "reason": reason},
        )
        published = {
            "type": "listing.status",
            "hunt_id": hunt.id,
            "listing_id": row.id,
            "short_id": row.short_id,
            "status": row.status,
        }
        payload = {"listing": _public(row)}
    _publish(published)
    return payload


def delete_listing(
    token: str | None, ip: str, listing_id: str, *, hard: bool
) -> dict[str, Any] | Error:
    published: dict[str, Any] | None = None
    with session_scope() as db:
        actor = _actor(db, token, ip)
        if actor is None:
            return "unauthenticated"
        row = db.get(Listing, listing_id)
        if row is None:
            return "missing"
        hunt = _open_hunt(db, actor, row.hunt_id, "owner", "listings:write")
        if isinstance(hunt, str):
            return hunt
        if hard:
            if actor.kind != "user" or not actor.is_admin:
                return "forbidden"
            add_event(
                db,
                type="listing.hard_deleted",
                actor_type=actor.kind,
                actor_id=actor.id,
                hunt_id=hunt.id,
                listing_id=row.id,
                payload={"short_id": row.short_id, "hard": True},
            )
            published = {
                "type": "listing.status",
                "hunt_id": hunt.id,
                "listing_id": row.id,
                "short_id": row.short_id,
                "status": "dead",
            }
            db.delete(row)
            return {"deleted": True, "hard": True}
        if _apply_status(row, "dead", None):
            return "invalid"
        row.notes = row.notes or "deleted by agent"
        row.updated_at = utcnow()
        row.is_presentable = presentable(hunt, row)
        add_event(
            db,
            type="listing.status",
            actor_type=actor.kind,
            actor_id=actor.id,
            hunt_id=hunt.id,
            listing_id=row.id,
            payload={"status": "dead", "reason": "deleted by agent"},
        )
        published = {
            "type": "listing.status",
            "hunt_id": hunt.id,
            "listing_id": row.id,
            "short_id": row.short_id,
            "status": "dead",
        }
        payload = {"listing": _public(row), "deleted": False, "hard": False}
    _publish(published)
    return payload


def mark_checked(token: str | None, ip: str, listing_id: str) -> dict[str, Any] | Error:
    with session_scope() as db:
        actor = _actor(db, token, ip)
        if actor is None:
            return "unauthenticated"
        row = db.get(Listing, listing_id)
        if row is None:
            return "missing"
        opened = _open_hunt(db, actor, row.hunt_id, "owner", "listings:write")
        if isinstance(opened, str):
            return opened
        now = utcnow()
        row.last_seen = now
        row.availability_checked_at = now
        row.updated_at = now
        add_event(
            db,
            type="listing.checked",
            actor_type=actor.kind,
            actor_id=actor.id,
            hunt_id=row.hunt_id,
            listing_id=row.id,
            payload={},
        )
        return {"listing": _public(row)}


def _rating_filter(stmt: Any, actor: Actor, query: dict[str, str]) -> Any:
    if actor.kind != "user":
        asked = query.get("min_stars") or query.get("passed") == "true"
        if asked or query.get("unrated") == "true":
            return "invalid"
        return stmt
    mine = and_(Rating.listing_id == Listing.id, Rating.user_id == actor.id)
    if query.get("passed") == "true":
        return stmt.join(Rating, mine).where(Rating.passed.is_(True))
    raw = query.get("min_stars")
    if raw:
        try:
            floor = int(raw)
        except ValueError:
            return "invalid"
        if floor < 1:
            return "invalid"
        return stmt.join(Rating, mine).where(Rating.passed.is_(False), Rating.stars >= floor)
    if query.get("unrated") == "true":
        return stmt.outerjoin(Rating, mine).where(Rating.id.is_(None))
    return stmt


def set_rating(
    token: str | None,
    ip: str,
    listing_id: str,
    *,
    stars: int | None,
    passed: bool,
) -> dict[str, Any] | Error:
    with session_scope() as db:
        actor = _actor(db, token, ip)
        if actor is None:
            return "unauthenticated"
        if actor.kind != "user":
            return "forbidden"
        row = db.get(Listing, listing_id)
        if row is None:
            return "missing"
        opened = _open_hunt(db, actor, row.hunt_id, "rater", "listings:read")
        if isinstance(opened, str):
            return opened
        if not _listing_visible(db, actor, row):
            return "missing"
        scale = opened.rating_scale
        if passed:
            stars = None
        elif stars is None or stars < 1 or stars > scale:
            return "invalid"
        existing = db.scalar(
            select(Rating).where(Rating.listing_id == row.id, Rating.user_id == actor.id)
        )
        now = utcnow()
        if existing is None:
            existing = Rating(
                listing_id=row.id,
                user_id=actor.id,
                stars=stars,
                passed=passed,
                updated_at=now,
            )
            db.add(existing)
        else:
            existing.stars = stars
            existing.passed = passed
            existing.updated_at = now
        add_event(
            db,
            type="listing.rated",
            actor_type="user",
            actor_id=actor.id,
            hunt_id=row.hunt_id,
            listing_id=row.id,
            payload={"stars": stars, "passed": passed},
        )
        db.flush()
        return {"stars": existing.stars, "passed": existing.passed}


def _cursor(row: Listing, sort: str) -> str:
    if sort == "price":
        value = str(row.price)
    elif sort == "hunt_score":
        value = "" if row.hunt_score is None else str(row.hunt_score)
    else:
        value = row.created_at.isoformat()
    raw = f"{value}|{row.id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[str, str] | None:
    padding = "=" * (-len(cursor) % 4)
    try:
        text = base64.urlsafe_b64decode(cursor + padding).decode()
        value, listing_id = text.split("|", 1)
    except (ValueError, UnicodeError):
        return None
    return value, listing_id


def list_listings(
    token: str | None, ip: str, query: dict[str, str]
) -> dict[str, Any] | Error:
    with session_scope() as db:
        actor = _actor(db, token, ip)
        if actor is None:
            return "unauthenticated"
        hunt_id = query.get("hunt_id") or actor.hunt_id or ""
        opened = _open_hunt(db, actor, hunt_id, "viewer", "listings:read")
        if isinstance(opened, str):
            return opened
        sort = query.get("sort", "newest")
        if sort not in SORTS:
            return "invalid"
        order_sort = "newest" if sort in {"predicted", "combined"} else sort
        stmt = select(Listing).where(Listing.hunt_id == hunt_id)
        if query.get("presentable", "true") != "false":
            stmt = stmt.where(Listing.is_presentable.is_(True))
        for key in ("status", "scam_risk", "geo_bucket", "unit_kind"):
            if query.get(key):
                stmt = stmt.where(getattr(Listing, key) == query[key])
        if query.get("min_price"):
            stmt = stmt.where(Listing.price >= float(query["min_price"]))
        if query.get("max_price"):
            stmt = stmt.where(Listing.price <= float(query["max_price"]))
        if query.get("q"):
            stmt = stmt.where(Listing.title.ilike(f"%{query['q']}%"))
        if actor.kind == "user":
            allowed = agent_allowlist(db, actor.id, hunt_id, is_admin=actor.is_admin)
            if allowed is not None:
                if allowed:
                    stmt = stmt.where(
                        or_(
                            Listing.created_by_agent.is_(None),
                            Listing.created_by_agent.in_(allowed),
                        )
                    )
                else:
                    stmt = stmt.where(Listing.created_by_agent.is_(None))
        if query.get("flag"):
            stmt = stmt.where(cast(Listing.honesty_flags, String).contains(f'"{query["flag"]}"'))
        if query.get("link_ok") == "false":
            stmt = stmt.where(Listing.link_ok.is_(False))
        elif query.get("link_ok") == "true":
            stmt = stmt.where(Listing.link_ok.is_(True))
        rated = _rating_filter(stmt, actor, query)
        if rated == "invalid":
            return "invalid"
        stmt = rated
        cursor = query.get("cursor")
        if cursor:
            decoded = _decode_cursor(cursor)
            if decoded is None:
                return "invalid"
            value, listing_id = decoded
            if order_sort == "price":
                stmt = stmt.where(
                    or_(
                        Listing.price > float(value),
                        and_(Listing.price == float(value), Listing.id > listing_id),
                    )
                )
            elif order_sort == "hunt_score":
                score = None if value == "" else float(value)
                if score is None:
                    stmt = stmt.where(Listing.hunt_score.is_(None) & (Listing.id > listing_id))
                else:
                    stmt = stmt.where(
                        or_(
                            Listing.hunt_score < score,
                            and_(Listing.hunt_score == score, Listing.id > listing_id),
                        )
                    )
            else:
                when = datetime.fromisoformat(value)
                stmt = stmt.where(
                    or_(
                        Listing.created_at < when,
                        and_(Listing.created_at == when, Listing.id < listing_id),
                    )
                )
        limit = min(int(query.get("limit", "50")), 100)
        if order_sort == "price":
            stmt = stmt.order_by(Listing.price.asc(), Listing.id.asc())
        elif order_sort == "hunt_score":
            stmt = stmt.order_by(Listing.hunt_score.desc(), Listing.id.asc())
        else:
            stmt = stmt.order_by(Listing.created_at.desc(), Listing.id.desc())
        rows = list(db.scalars(stmt.limit(limit + 1)).all())
        page = rows[:limit]
        next_cursor = _cursor(page[-1], order_sort) if len(rows) > limit and page else None
        grouped = photos_by_listing(db, [row.id for row in page])
        bodies = [_public(row, grouped.get(row.id, [])) for row in page]
        _stamp_ratings(db, actor, page, bodies)
        return {
            "listings": bodies,
            "next_cursor": next_cursor,
        }


def get_listing(
    token: str | None, ip: str, ref: str, hunt_id: str | None
) -> dict[str, Any] | Error:
    with session_scope() as db:
        actor = _actor(db, token, ip)
        if actor is None:
            return "unauthenticated"
        short = ref[1:] if ref.startswith("#") else ref
        row: Listing | None
        if short.isdigit():
            if actor.kind == "agent" and actor.hunt_id:
                member_hunts = select(Hunt.id).where(Hunt.id == actor.hunt_id)
            else:
                member_hunts = select(HuntMember.hunt_id).where(HuntMember.user_id == actor.id)
            stmt = select(Listing).where(
                Listing.short_id == int(short), Listing.hunt_id.in_(member_hunts)
            )
            if hunt_id:
                stmt = stmt.where(Listing.hunt_id == hunt_id)
            found = list(db.scalars(stmt).all())
            row = found[0] if len(found) == 1 else None
        else:
            row = db.get(Listing, ref)
        if row is None:
            return "missing"
        opened = _open_hunt(db, actor, row.hunt_id, "viewer", "listings:read")
        if isinstance(opened, str):
            return opened
        if not _listing_visible(db, actor, row):
            return "missing"
        body = _detail(db, row)
        _stamp_ratings(db, actor, [row], [body])
        return body


def add_comment(
    token: str | None, ip: str, listing_id: str, text: str
) -> dict[str, Any] | Error:
    cleaned = text.strip()
    if not cleaned or len(cleaned) > 2000:
        return "invalid"
    with session_scope() as db:
        actor = _actor(db, token, ip)
        if actor is None:
            return "unauthenticated"
        row = db.get(Listing, listing_id)
        if row is None:
            return "missing"
        if actor.kind == "agent":
            if actor.hunt_id != row.hunt_id:
                return "missing"
        else:
            opened = _open_hunt(db, actor, row.hunt_id, "viewer", "listings:read")
            if isinstance(opened, str):
                return opened
            if not _listing_visible(db, actor, row):
                return "missing"
        note = Comment(
            listing_id=row.id,
            author_user_id=actor.id if actor.kind == "user" else None,
            author_agent_id=actor.id if actor.kind == "agent" else None,
            text=cleaned,
        )
        db.add(note)
        db.flush()
        add_event(
            db,
            type="listing.comment",
            actor_type=actor.kind,
            actor_id=actor.id,
            hunt_id=row.hunt_id,
            listing_id=row.id,
            payload={"comment_id": note.id},
        )
        return {
            "id": note.id,
            "text": note.text,
            "author_type": actor.kind,
            "author_user_id": note.author_user_id,
            "author_agent_id": note.author_agent_id,
            "created_at": note.created_at.isoformat(),
        }


def member_hunt_ids(token: str | None, ip: str) -> set[str] | None:
    with session_scope() as db:
        actor = _actor(db, token, ip)
        if actor is None:
            return None
        if actor.kind == "agent" and actor.hunt_id:
            return {actor.hunt_id}
        rows = db.scalars(select(HuntMember.hunt_id).where(HuntMember.user_id == actor.id)).all()
        return set(rows)


def stream_events(allowed: set[str]) -> Any:
    mailbox = hub.subscribe()
    try:
        yield "event: hello\ndata: {}\n\n"
        while True:
            try:
                item = mailbox.get(timeout=15)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            if item.get("hunt_id") not in allowed:
                continue
            name = str(item.get("type", "listing"))
            yield f"event: {name}\ndata: {json.dumps(item)}\n\n"
    finally:
        hub.unsubscribe(mailbox)
