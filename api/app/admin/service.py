from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.models import Agent
from app.auth.models import User
from app.auth.passwords import PasswordRejected, hash_password
from app.auth.service import (
    ROLES,
    _load_live_session,
    normalize_email,
    session_is_recent,
    valid_email,
)
from app.core.db import session_scope
from app.events.service import add_event
from app.tenancy.models import Hunt, HuntMember, MemberAgentGrant

AdminError = Literal["unauthenticated", "forbidden", "stale", "invalid", "conflict", "missing"]


def _prepare_grants(
    db: Session, grants: list[dict[str, Any]]
) -> list[tuple[str, str, list[str] | None]] | Literal["invalid"]:
    prepared: list[tuple[str, str, list[str] | None]] = []
    seen: set[str] = set()
    for grant in grants:
        hunt_id = str(grant.get("hunt_id", ""))
        role = str(grant.get("role", "viewer"))
        if not hunt_id or hunt_id in seen or role not in ROLES:
            return "invalid"
        seen.add(hunt_id)
        if db.get(Hunt, hunt_id) is None:
            return "invalid"
        raw_agents = grant.get("agent_ids", None)
        agent_ids: list[str] | None
        if raw_agents is None:
            agent_ids = None
        elif isinstance(raw_agents, list) and all(isinstance(item, str) for item in raw_agents):
            agent_ids = list(dict.fromkeys(raw_agents))
        else:
            return "invalid"
        if agent_ids is not None:
            for agent_id in agent_ids:
                agent = db.get(Agent, agent_id)
                if agent is None or agent.hunt_id != hunt_id:
                    return "invalid"
        prepared.append((hunt_id, role, agent_ids))
    return prepared


def _write_grants(
    db: Session, user: User, prepared: list[tuple[str, str, list[str] | None]]
) -> None:
    members = db.scalars(select(HuntMember).where(HuntMember.user_id == user.id)).all()
    for member in members:
        db.delete(member)
    rows = db.scalars(select(MemberAgentGrant).where(MemberAgentGrant.user_id == user.id)).all()
    for row in rows:
        db.delete(row)
    db.flush()
    label = user.display_name[:80] or "Member"
    for hunt_id, role, agent_ids in prepared:
        db.add(
            HuntMember(
                hunt_id=hunt_id,
                user_id=user.id,
                role=role,
                rater_label=label,
                agents_restricted=agent_ids is not None,
            )
        )
        if agent_ids is None:
            continue
        for agent_id in agent_ids:
            db.add(MemberAgentGrant(hunt_id=hunt_id, user_id=user.id, agent_id=agent_id))
    db.flush()


def _public(db: Session, user: User) -> dict[str, Any]:
    members = db.scalars(select(HuntMember).where(HuntMember.user_id == user.id)).all()
    grants: list[dict[str, Any]] = []
    for member in members:
        hunt = db.get(Hunt, member.hunt_id)
        agent_ids: list[str] | None = None
        if member.agents_restricted:
            agent_ids = list(
                db.scalars(
                    select(MemberAgentGrant.agent_id).where(
                        MemberAgentGrant.hunt_id == member.hunt_id,
                        MemberAgentGrant.user_id == user.id,
                    )
                ).all()
            )
        grants.append(
            {
                "hunt_id": member.hunt_id,
                "hunt_name": hunt.name if hunt is not None else "",
                "role": member.role,
                "agent_ids": agent_ids,
            }
        )
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "is_admin": user.is_admin,
        "grants": grants,
    }


def _require_admin(db: Session, token: str, ip: str, *, recent: bool) -> User | AdminError:
    found = _load_live_session(db, token, ip)
    if found is None:
        return "unauthenticated"
    user, row = found
    if not user.is_admin:
        return "forbidden"
    if recent and not session_is_recent(row):
        return "stale"
    return user


def list_feeds(token: str, ip: str) -> dict[str, Any] | AdminError:
    with session_scope() as db:
        admin = _require_admin(db, token, ip, recent=False)
        if isinstance(admin, str):
            return admin
        hunts = db.scalars(select(Hunt).order_by(Hunt.name.asc())).all()
        feeds = []
        for hunt in hunts:
            agents = db.scalars(select(Agent).where(Agent.hunt_id == hunt.id)).all()
            feeds.append(
                {
                    "id": hunt.id,
                    "name": hunt.name,
                    "slug": hunt.slug,
                    "agents": [
                        {
                            "id": agent.id,
                            "name": agent.name,
                            "revoked": agent.revoked_at is not None,
                        }
                        for agent in agents
                    ],
                }
            )
        return {"feeds": feeds}


def list_people(token: str, ip: str) -> dict[str, Any] | AdminError:
    with session_scope() as db:
        admin = _require_admin(db, token, ip, recent=False)
        if isinstance(admin, str):
            return admin
        users = db.scalars(select(User).order_by(User.created_at.asc())).all()
        return {"users": [_public(db, user) for user in users]}


def create_person(
    token: str,
    ip: str,
    *,
    email: str,
    display_name: str,
    password: str,
    grants: list[dict[str, Any]],
) -> dict[str, Any] | AdminError | PasswordRejected:
    email_norm = normalize_email(email)
    name = display_name.strip()
    if not valid_email(email_norm) or not name:
        return "invalid"
    try:
        password_hash = hash_password(password)
    except PasswordRejected as exc:
        return exc
    with session_scope() as db:
        admin = _require_admin(db, token, ip, recent=True)
        if isinstance(admin, str):
            return admin
        if db.scalar(select(User).where(User.email == email_norm)) is not None:
            return "conflict"
        prepared = _prepare_grants(db, grants)
        if isinstance(prepared, str):
            return prepared
        user = User(
            email=email_norm,
            display_name=name[:120],
            password_hash=password_hash,
            is_admin=False,
        )
        db.add(user)
        db.flush()
        _write_grants(db, user, prepared)
        add_event(
            db,
            type="admin.user_created",
            actor_type="user",
            actor_id=admin.id,
            payload={"user_id": user.id, "email": email_norm},
        )
        return _public(db, user)


def replace_access(
    token: str,
    ip: str,
    user_id: str,
    grants: list[dict[str, Any]],
) -> dict[str, Any] | AdminError:
    with session_scope() as db:
        admin = _require_admin(db, token, ip, recent=True)
        if isinstance(admin, str):
            return admin
        user = db.get(User, user_id)
        if user is None:
            return "missing"
        if user.is_admin:
            return "forbidden"
        prepared = _prepare_grants(db, grants)
        if isinstance(prepared, str):
            return prepared
        _write_grants(db, user, prepared)
        add_event(
            db,
            type="admin.access_updated",
            actor_type="user",
            actor_id=admin.id,
            payload={"user_id": user.id},
        )
        return _public(db, user)
