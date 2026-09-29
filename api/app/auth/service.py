import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.models import Invite, LoginThrottle, RecoveryLink, SessionRow, User
from app.auth.passwords import PasswordRejected, dummy_verify, hash_password, verify_password
from app.core.clock import as_utc, utcnow
from app.core.config import get_settings
from app.core.db import session_scope
from app.events.service import add_event

IDLE_SHORT = timedelta(hours=12)
IDLE_TRUSTED = timedelta(days=30)
STEP_UP = timedelta(minutes=10)
MAX_BACKOFF_SECONDS = 15 * 60
ROLES = {"owner", "rater", "viewer"}

LoginCode = Literal["invalid", "step_up", "locked"]


@dataclass
class AuthSession:
    token: str
    user: dict[str, Any]
    expires_at: datetime


@dataclass
class LoginDenied:
    code: LoginCode


def normalize_email(email: str) -> str:
    return email.strip().lower()


def valid_email(email: str) -> bool:
    if " " in email or "@" not in email:
        return False
    local, _, domain = email.partition("@")
    return bool(local) and "." in domain


def user_public(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "is_admin": user.is_admin,
        "require_passkey": user.require_passkey,
        "has_password": user.password_hash is not None,
    }


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def session_id(token: str) -> str:
    return _token_hash(token)


def _subjects(email: str, ip: str) -> tuple[str, str]:
    return (f"acct:{email}", f"ip:{ip}")


def _locked(db: Session, subjects: tuple[str, str], now: datetime) -> bool:
    for subject in subjects:
        row = db.get(LoginThrottle, subject)
        if row is not None and row.locked_until is not None and as_utc(row.locked_until) > now:
            return True
    return False


def _bump(db: Session, subjects: tuple[str, str], now: datetime) -> None:
    for subject in subjects:
        row = db.get(LoginThrottle, subject)
        if row is not None and row.locked_until is not None and as_utc(row.locked_until) > now:
            continue
        if row is None:
            row = LoginThrottle(subject=subject, failures=0)
            db.add(row)
        row.failures += 1
        delay = min(2 ** (row.failures - 1), MAX_BACKOFF_SECONDS)
        row.locked_until = now + timedelta(seconds=delay)


def _clear(db: Session, subjects: tuple[str, str]) -> None:
    for subject in subjects:
        row = db.get(LoginThrottle, subject)
        if row is not None:
            db.delete(row)


def device_label_from_agent(user_agent: str) -> str:
    lowered = user_agent.lower()
    if "iphone" in lowered:
        return "iPhone"
    if "ipad" in lowered:
        return "iPad"
    if "android" in lowered:
        return "Android"
    if "mac os" in lowered or "macintosh" in lowered:
        return "Mac"
    if "windows" in lowered:
        return "Windows"
    if "linux" in lowered:
        return "Linux"
    return "Browser"


def _issue_session(
    db: Session,
    user: User,
    *,
    ip: str,
    user_agent: str,
    trust_device: bool,
    auth_method: str,
    device_label: str | None,
) -> tuple[str, datetime]:
    now = utcnow()
    raw = secrets.token_urlsafe(32)
    trusted_until = now + IDLE_TRUSTED if trust_device else None
    expires_at = now + (IDLE_TRUSTED if trust_device else IDLE_SHORT)
    db.add(
        SessionRow(
            id=_token_hash(raw),
            user_id=user.id,
            device_label=device_label or device_label_from_agent(user_agent),
            user_agent=user_agent[:400],
            ip_first=ip,
            ip_last=ip,
            auth_method=auth_method,
            created_at=now,
            last_seen_at=now,
            expires_at=expires_at,
            trusted_until=trusted_until,
            reauthenticated_at=now,
        )
    )
    return raw, expires_at


def setup_admin(
    *,
    token: str,
    email: str,
    password: str,
    display_name: str,
    ip: str,
    user_agent: str,
) -> AuthSession | Literal["closed", "invalid", "rejected"] | PasswordRejected:
    settings = get_settings()
    if not settings.admin_email or not settings.admin_bootstrap_token:
        return "closed"
    with session_scope() as db:
        existing = db.scalar(select(func.count()).select_from(User)) or 0
        if existing:
            return "closed"
        expected_email = normalize_email(settings.admin_email)
        email_norm = normalize_email(email)
        token_ok = hmac.compare_digest(token, settings.admin_bootstrap_token)
        if not token_ok or email_norm != expected_email or not valid_email(email_norm):
            add_event(
                db,
                type="auth.setup_failed",
                actor_type="system",
                actor_id=None,
                payload={"email": email_norm},
            )
            return "invalid"
        if not display_name.strip():
            return "rejected"
        try:
            password_hash = hash_password(password)
        except PasswordRejected as exc:
            return exc
        user = User(
            email=email_norm,
            display_name=display_name.strip()[:120],
            password_hash=password_hash,
            is_admin=True,
        )
        db.add(user)
        db.flush()
        raw, expires_at = _issue_session(
            db,
            user,
            ip=ip,
            user_agent=user_agent,
            trust_device=False,
            auth_method="password",
            device_label=None,
        )
        add_event(
            db,
            type="auth.setup",
            actor_type="user",
            actor_id=user.id,
            payload={"email": user.email},
        )
        return AuthSession(token=raw, user=user_public(user), expires_at=expires_at)


def login_with_password(
    *,
    email: str,
    password: str,
    ip: str,
    user_agent: str,
    trust_device: bool,
    device_label: str | None,
) -> AuthSession | LoginDenied:
    email_norm = normalize_email(email)
    subjects = _subjects(email_norm, ip)
    now = utcnow()
    with session_scope() as db:
        user = db.scalar(select(User).where(User.email == email_norm))
        locked = _locked(db, subjects, now)
        if user is None or user.password_hash is None or user.disabled_at is not None:
            dummy_verify(password)
            password_ok = False
        else:
            password_ok = verify_password(user.password_hash, password)
        if locked:
            add_event(
                db,
                type="auth.login_locked",
                actor_type="user" if user else "system",
                actor_id=user.id if user else None,
                payload={"email": email_norm},
            )
            return LoginDenied("locked")
        if not password_ok or user is None or user.disabled_at is not None:
            _bump(db, subjects, now)
            add_event(
                db,
                type="auth.login_failed",
                actor_type="user" if user else "system",
                actor_id=user.id if user else None,
                payload={"email": email_norm},
            )
            return LoginDenied("invalid")
        if user.require_passkey:
            add_event(
                db,
                type="auth.step_up_needed",
                actor_type="user",
                actor_id=user.id,
                payload={},
            )
            return LoginDenied("step_up")
        _clear(db, subjects)
        raw, expires_at = _issue_session(
            db,
            user,
            ip=ip,
            user_agent=user_agent,
            trust_device=trust_device,
            auth_method="password",
            device_label=device_label,
        )
        add_event(
            db,
            type="auth.login",
            actor_type="user",
            actor_id=user.id,
            payload={"method": "password", "trust_device": trust_device},
        )
        return AuthSession(token=raw, user=user_public(user), expires_at=expires_at)


def _load_live_session(db: Session, token: str, ip: str) -> tuple[User, SessionRow] | None:
    row = db.get(SessionRow, _token_hash(token))
    if row is None or row.revoked_at is not None:
        return None
    now = utcnow()
    if as_utc(row.expires_at) <= now:
        return None
    user = db.get(User, row.user_id)
    if user is None or user.disabled_at is not None:
        return None
    window = IDLE_TRUSTED if row.trusted_until and as_utc(row.trusted_until) > now else IDLE_SHORT
    row.last_seen_at = now
    row.expires_at = now + window
    row.ip_last = ip
    return user, row


def touch_session(token: str, ip: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    with session_scope() as db:
        found = _load_live_session(db, token, ip)
        if found is None:
            return None
        user, row = found
        return user_public(user), _session_public(row, token)


def list_sessions(token: str, ip: str) -> list[dict[str, Any]] | None:
    with session_scope() as db:
        found = _load_live_session(db, token, ip)
        if found is None:
            return None
        user, current = found
        rows = db.scalars(
            select(SessionRow)
            .where(SessionRow.user_id == user.id, SessionRow.revoked_at.is_(None))
            .order_by(SessionRow.created_at.desc())
        ).all()
        return [_session_public(row, token if row.id == current.id else None) for row in rows]


def _session_public(row: SessionRow, current_token: str | None) -> dict[str, Any]:
    current = current_token is not None and _token_hash(current_token) == row.id
    return {
        "id": row.id,
        "device_label": row.device_label,
        "user_agent": row.user_agent,
        "ip_first": row.ip_first,
        "ip_last": row.ip_last,
        "auth_method": row.auth_method,
        "created_at": as_utc(row.created_at).isoformat(),
        "last_seen_at": as_utc(row.last_seen_at).isoformat(),
        "expires_at": as_utc(row.expires_at).isoformat(),
        "trusted_until": as_utc(row.trusted_until).isoformat() if row.trusted_until else None,
        "current": current,
    }


def revoke_session(
    token: str, ip: str, session_id: str
) -> Literal["ok", "missing", "unauthenticated"]:
    with session_scope() as db:
        found = _load_live_session(db, token, ip)
        if found is None:
            return "unauthenticated"
        user, _current = found
        row = db.get(SessionRow, session_id)
        if row is None or row.user_id != user.id or row.revoked_at is not None:
            return "missing"
        row.revoked_at = utcnow()
        add_event(
            db,
            type="auth.session_revoked",
            actor_type="user",
            actor_id=user.id,
            payload={"session_id": session_id},
        )
        return "ok"


def session_is_recent(row: SessionRow) -> bool:
    return as_utc(row.reauthenticated_at) >= utcnow() - STEP_UP


def revoke_all_sessions(token: str, ip: str) -> bool:
    with session_scope() as db:
        found = _load_live_session(db, token, ip)
        if found is None:
            return False
        user, _current = found
        rows = db.scalars(
            select(SessionRow).where(
                SessionRow.user_id == user.id,
                SessionRow.revoked_at.is_(None),
            )
        ).all()
        now = utcnow()
        for row in rows:
            row.revoked_at = now
        add_event(
            db,
            type="auth.sessions_revoked_all",
            actor_type="user",
            actor_id=user.id,
            payload={"count": len(rows)},
        )
        return True


def revoke_other_sessions(token: str, ip: str) -> bool:
    with session_scope() as db:
        found = _load_live_session(db, token, ip)
        if found is None:
            return False
        user, current = found
        rows = db.scalars(
            select(SessionRow).where(
                SessionRow.user_id == user.id,
                SessionRow.revoked_at.is_(None),
                SessionRow.id != current.id,
            )
        ).all()
        now = utcnow()
        for row in rows:
            row.revoked_at = now
        add_event(
            db,
            type="auth.sessions_revoked_others",
            actor_type="user",
            actor_id=user.id,
            payload={"count": len(rows)},
        )
        return True


def change_password(
    token: str,
    ip: str,
    *,
    password: str,
    current_password: str | None,
) -> Literal["ok", "unauthenticated", "stale", "invalid_current"] | PasswordRejected:
    with session_scope() as db:
        found = _load_live_session(db, token, ip)
        if found is None:
            return "unauthenticated"
        user, row = found
        if as_utc(row.reauthenticated_at) < utcnow() - STEP_UP:
            return "stale"
        if user.password_hash is not None:
            if not current_password or not verify_password(user.password_hash, current_password):
                dummy_verify(password)
                return "invalid_current"
        else:
            dummy_verify(current_password or "")
        try:
            user.password_hash = hash_password(password)
        except PasswordRejected as exc:
            return exc
        add_event(
            db,
            type="auth.password_changed",
            actor_type="user",
            actor_id=user.id,
            payload={},
        )
        return "ok"


def create_invite(
    token: str,
    ip: str,
    *,
    role: str,
    email: str | None,
    hunt_id: str | None,
) -> dict[str, Any] | Literal["unauthenticated", "forbidden", "stale", "invalid"]:
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
        if not user.is_admin:
            return "forbidden"
        if as_utc(row.reauthenticated_at) < utcnow() - STEP_UP:
            return "stale"
        raw = secrets.token_urlsafe(32)
        expires_at = utcnow() + timedelta(days=7)
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
            type="auth.invite_created",
            actor_type="user",
            actor_id=user.id,
            payload={"role": role, "email": email_norm, "hunt_id": hunt_id},
        )
        return {
            "token": raw,
            "expires_at": expires_at.isoformat(),
            "role": role,
            "email": email_norm,
        }


def accept_invite(
    *,
    token: str,
    email: str,
    password: str,
    display_name: str,
    ip: str,
    user_agent: str,
) -> AuthSession | Literal["invalid", "rejected"] | PasswordRejected:
    email_norm = normalize_email(email)
    if not valid_email(email_norm) or not display_name.strip():
        return "rejected"
    with session_scope() as db:
        invite = db.scalar(select(Invite).where(Invite.token_hash == _token_hash(token)))
        now = utcnow()
        if (
            invite is None
            or invite.used_at is not None
            or as_utc(invite.expires_at) <= now
            or (invite.email and invite.email != email_norm)
        ):
            return "invalid"
        if db.scalar(select(User).where(User.email == email_norm)) is not None:
            return "invalid"
        try:
            password_hash = hash_password(password)
        except PasswordRejected as exc:
            return exc
        user = User(
            email=email_norm,
            display_name=display_name.strip()[:120],
            password_hash=password_hash,
            is_admin=False,
        )
        db.add(user)
        db.flush()
        if invite.hunt_id:
            from app.tenancy.models import HuntMember

            db.add(
                HuntMember(
                    hunt_id=invite.hunt_id,
                    user_id=user.id,
                    role=invite.role,
                    rater_label=display_name.strip()[:80],
                )
            )
        invite.used_by = user.id
        invite.used_at = now
        raw, expires_at = _issue_session(
            db,
            user,
            ip=ip,
            user_agent=user_agent,
            trust_device=False,
            auth_method="password",
            device_label=None,
        )
        add_event(
            db,
            type="auth.invite_accepted",
            actor_type="user",
            actor_id=user.id,
            payload={"invite_id": invite.id, "role": invite.role, "hunt_id": invite.hunt_id},
        )
        return AuthSession(token=raw, user=user_public(user), expires_at=expires_at)


def issue_recovery_link(email: str) -> str | None:
    email_norm = normalize_email(email)
    settings = get_settings()
    with session_scope() as db:
        user = db.scalar(select(User).where(User.email == email_norm))
        if user is None:
            return None
        raw = secrets.token_urlsafe(32)
        db.add(
            RecoveryLink(
                token_hash=_token_hash(raw),
                user_id=user.id,
                expires_at=utcnow() + timedelta(minutes=30),
            )
        )
        add_event(
            db,
            type="auth.recovery_issued",
            actor_type="system",
            actor_id=user.id,
            payload={},
        )
        return f"{settings.public_url.rstrip('/')}/recover?token={raw}"


def recover_password(token: str, password: str) -> Literal["ok", "invalid"] | PasswordRejected:
    with session_scope() as db:
        link = db.scalar(select(RecoveryLink).where(RecoveryLink.token_hash == _token_hash(token)))
        if link is None or link.used_at is not None or as_utc(link.expires_at) <= utcnow():
            return "invalid"
        user = db.get(User, link.user_id)
        if user is None or user.disabled_at is not None:
            return "invalid"
        try:
            user.password_hash = hash_password(password)
        except PasswordRejected as exc:
            return exc
        link.used_at = utcnow()
        add_event(
            db,
            type="auth.password_reset",
            actor_type="user",
            actor_id=user.id,
            payload={},
        )
        return "ok"
