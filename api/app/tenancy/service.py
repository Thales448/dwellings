import re
import secrets
from datetime import timedelta
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.models import Invite, User
from app.auth.service import ROLES, _load_live_session, normalize_email, user_public, valid_email
from app.core.clock import utcnow
from app.core.db import session_scope
from app.events.service import add_event
from app.tenancy.models import Hunt, HuntMember, MemberAgentGrant

RANK = {"viewer": 1, "rater": 2, "owner": 3}
Access = Literal["missing", "forbidden"]


def _hunt_public(hunt: Hunt, role: str) -> dict[str, Any]:
    return {
        "id": hunt.id,
        "slug": hunt.slug,
        "name": hunt.name,
        "kind": hunt.kind,
        "schema": hunt.schema_id,
        "criteria": hunt.criteria,
        "rating_scale": hunt.rating_scale,
        "rating_weights": hunt.rating_weights,
        "role": role,
    }


def _member_public(member: HuntMember, user: User) -> dict[str, Any]:
    return {
        "user_id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": member.role,
        "rater_label": member.rater_label,
    }


def agent_allowlist(db: Session, user_id: str, hunt_id: str, *, is_admin: bool) -> set[str] | None:
    if is_admin:
        return None
    member = db.get(HuntMember, (hunt_id, user_id))
    if member is None or not member.agents_restricted:
        return None
    rows = db.scalars(
        select(MemberAgentGrant.agent_id).where(
            MemberAgentGrant.hunt_id == hunt_id,
            MemberAgentGrant.user_id == user_id,
        )
    ).all()
    return set(rows)


def require_hunt(
    db: Session, user_id: str, hunt_id: str, minimum: str
) -> tuple[Hunt, HuntMember] | Access:
    hunt = db.get(Hunt, hunt_id)
    if hunt is None:
        return "missing"
    member = db.get(HuntMember, (hunt_id, user_id))
    if member is None:
        return "missing"
    if RANK[member.role] < RANK[minimum]:
        return "forbidden"
    return hunt, member


def list_my_hunts(token: str, ip: str) -> list[dict[str, Any]] | None:
    with session_scope() as db:
        found = _load_live_session(db, token, ip)
        if found is None:
            return None
        user, _row = found
        members = db.scalars(select(HuntMember).where(HuntMember.user_id == user.id)).all()
        hunts = []
        for member in members:
            hunt = db.get(Hunt, member.hunt_id)
            if hunt is not None:
                hunts.append(_hunt_public(hunt, member.role))
        return hunts


def me(token: str, ip: str) -> dict[str, Any] | None:
    with session_scope() as db:
        found = _load_live_session(db, token, ip)
        if found is None:
            return None
        user, _row = found
        public = user_public(user)
    hunts = list_my_hunts(token, ip) or []
    public["hunts"] = hunts
    return public


def create_hunt(
    token: str, ip: str, body: dict[str, Any]
) -> dict[str, Any] | Literal["unauthenticated", "invalid", "conflict"]:
    name = str(body.get("name", "")).strip()
    slug = str(body.get("slug", "")).strip().lower()
    kind = body.get("kind")
    schema = str(body.get("schema", "")).strip()
    scale = body.get("rating_scale", 5)
    if not name or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        return "invalid"
    if kind not in {"rental", "purchase"} or not schema or scale not in {5, 10}:
        return "invalid"
    criteria = body.get("criteria") or {}
    weights = body.get("rating_weights") or {}
    if not isinstance(criteria, dict) or not isinstance(weights, dict):
        return "invalid"
    with session_scope() as db:
        found = _load_live_session(db, token, ip)
        if found is None:
            return "unauthenticated"
        user, _row = found
        if db.scalar(select(Hunt).where(Hunt.slug == slug)) is not None:
            return "conflict"
        hunt = Hunt(
            slug=slug,
            name=name[:120],
            kind=kind,
            schema_id=schema,
            criteria=criteria,
            rating_scale=scale,
            rating_weights=weights,
            created_by=user.id,
        )
        db.add(hunt)
        db.flush()
        db.add(
            HuntMember(
                hunt_id=hunt.id,
                user_id=user.id,
                role="owner",
                rater_label=user.display_name[:80],
            )
        )
        add_event(
            db,
            type="hunt.created",
            actor_type="user",
            actor_id=user.id,
            hunt_id=hunt.id,
            payload={"slug": slug},
        )
        return _hunt_public(hunt, "owner")


def get_hunt(
    token: str, ip: str, hunt_id: str
) -> dict[str, Any] | Access | Literal["unauthenticated"]:
    with session_scope() as db:
        found = _load_live_session(db, token, ip)
        if found is None:
            return "unauthenticated"
        user, _row = found
        access = require_hunt(db, user.id, hunt_id, "viewer")
        if isinstance(access, str):
            return access
        hunt, member = access
        return _hunt_public(hunt, member.role)


def update_hunt(
    token: str, ip: str, hunt_id: str, body: dict[str, Any]
) -> dict[str, Any] | Access | Literal["unauthenticated", "invalid"]:
    with session_scope() as db:
        found = _load_live_session(db, token, ip)
        if found is None:
            return "unauthenticated"
        user, _row = found
        access = require_hunt(db, user.id, hunt_id, "owner")
        if isinstance(access, str):
            return access
        hunt, member = access
        if "criteria" in body:
            if not isinstance(body["criteria"], dict):
                return "invalid"
            hunt.criteria = body["criteria"]
        if "rating_weights" in body:
            if not isinstance(body["rating_weights"], dict):
                return "invalid"
            hunt.rating_weights = body["rating_weights"]
        if "name" in body and str(body["name"]).strip():
            hunt.name = str(body["name"]).strip()[:120]
        add_event(
            db,
            type="hunt.updated",
            actor_type="user",
            actor_id=user.id,
            hunt_id=hunt.id,
            payload={},
        )
        return _hunt_public(hunt, member.role)


def list_members(
    token: str, ip: str, hunt_id: str
) -> list[dict[str, Any]] | Access | Literal["unauthenticated"]:
    with session_scope() as db:
        found = _load_live_session(db, token, ip)
        if found is None:
            return "unauthenticated"
        user, _row = found
        access = require_hunt(db, user.id, hunt_id, "viewer")
        if isinstance(access, str):
            return access
        members = db.scalars(select(HuntMember).where(HuntMember.hunt_id == hunt_id)).all()
        result = []
        for member in members:
            person = db.get(User, member.user_id)
            if person is not None:
                result.append(_member_public(member, person))
        return result


def remove_member(
    token: str, ip: str, hunt_id: str, user_id: str
) -> Access | Literal["unauthenticated", "ok", "invalid"]:
    with session_scope() as db:
        found = _load_live_session(db, token, ip)
        if found is None:
            return "unauthenticated"
        user, _row = found
        access = require_hunt(db, user.id, hunt_id, "owner")
        if isinstance(access, str):
            return access
        target = db.get(HuntMember, (hunt_id, user_id))
        if target is None:
            return "missing"
        if target.role == "owner":
            owners = db.scalar(
                select(func.count())
                .select_from(HuntMember)
                .where(HuntMember.hunt_id == hunt_id, HuntMember.role == "owner")
            )
            if (owners or 0) <= 1:
                return "invalid"
        db.delete(target)
        add_event(
            db,
            type="hunt.member_removed",
            actor_type="user",
            actor_id=user.id,
            hunt_id=hunt_id,
            payload={"user_id": user_id},
        )
        return "ok"


def invite_member(
    token: str,
    ip: str,
    hunt_id: str,
    *,
    role: str,
    email: str | None,
) -> dict[str, Any] | Access | Literal["unauthenticated", "invalid", "stale"]:
    if role not in ROLES:
        return "invalid"
    email_norm = normalize_email(email) if email else None
    if email_norm and not valid_email(email_norm):
        return "invalid"
    with session_scope() as db:
        found = _load_live_session(db, token, ip)
        if found is None:
            return "unauthenticated"
        user, row = found
        from app.auth.service import session_is_recent

        if not session_is_recent(row):
            return "stale"
        access = require_hunt(db, user.id, hunt_id, "owner")
        if isinstance(access, str):
            return access
        raw = secrets.token_urlsafe(32)
        expires_at = utcnow() + timedelta(days=7)
        from app.auth.service import _token_hash

        db.add(
            Invite(
                token_hash=_token_hash(raw),
                hunt_id=hunt_id,
                role=role,
                email=email_norm,
                expires_at=expires_at,
            )
        )
        add_event(
            db,
            type="hunt.invite_created",
            actor_type="user",
            actor_id=user.id,
            hunt_id=hunt_id,
            payload={"role": role, "email": email_norm},
        )
        return {
            "token": raw,
            "expires_at": expires_at.isoformat(),
            "role": role,
            "email": email_norm,
        }
