import json
import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import func, select
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url, encode_cbor, parse_cbor
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidRegistrationResponse,
)
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    CredentialDeviceType,
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialType,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.auth.models import User, WebAuthnChallenge, WebAuthnCredential
from app.auth.service import (
    AuthSession,
    _issue_session,
    _load_live_session,
    session_is_recent,
    user_public,
)
from app.core.clock import as_utc, utcnow
from app.core.config import get_settings
from app.core.db import session_scope
from app.events.service import add_event

CHALLENGE_TTL = timedelta(minutes=5)
PasskeyError = Literal["unauthenticated", "stale", "invalid", "missing", "last"]
logger = logging.getLogger(__name__)


@dataclass
class PasskeyRejected:
    detail: str


def _prepare_credential(credential: dict[str, Any]) -> dict[str, Any]:
    prepared = dict(credential)
    raw_id = prepared.get("rawId")
    if isinstance(raw_id, str):
        prepared["id"] = bytes_to_base64url(base64url_to_bytes(raw_id))
    response = prepared.get("response")
    if not isinstance(response, dict):
        return prepared
    attestation = response.get("attestationObject")
    if not isinstance(attestation, str):
        return prepared
    try:
        decoded = parse_cbor(base64url_to_bytes(attestation))
    except Exception:
        return prepared
    if not isinstance(decoded, dict) or decoded.get("fmt") == "none":
        return prepared
    if "authData" not in decoded:
        return prepared
    rewritten = {"fmt": "none", "attStmt": {}, "authData": decoded["authData"]}
    response = dict(response)
    response["attestationObject"] = bytes_to_base64url(encode_cbor(rewritten))
    prepared["response"] = response
    return prepared


@dataclass
class PasskeyStepUp:
    user: dict[str, Any]


def _options_payload(
    challenge: bytes, options: Any, *, user_id: str | None, kind: str
) -> dict[str, Any]:
    challenge_id = str(uuid4())
    with session_scope() as db:
        db.add(
            WebAuthnChallenge(
                id=challenge_id,
                user_id=user_id,
                challenge=bytes_to_base64url(challenge),
                kind=kind,
                expires_at=utcnow() + CHALLENGE_TTL,
            )
        )
    return {"challenge_id": challenge_id, "options": json.loads(options_to_json(options))}


def registration_options(
    token: str, ip: str
) -> dict[str, Any] | Literal["unauthenticated", "stale"]:
    settings = get_settings()
    with session_scope() as db:
        found = _load_live_session(db, token, ip)
        if found is None:
            return "unauthenticated"
        user, row = found
        if not session_is_recent(row):
            return "stale"
        existing = db.scalars(
            select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
        ).all()
        user_id = user.id
        email = user.email
        display_name = user.display_name
        exclude = [
            PublicKeyCredentialDescriptor(
                id=base64url_to_bytes(item.id),
                type=PublicKeyCredentialType.PUBLIC_KEY,
            )
            for item in existing
        ]
    challenge = secrets.token_bytes(32)
    options = generate_registration_options(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        user_name=email,
        user_display_name=display_name,
        user_id=user_id.encode(),
        challenge=challenge,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=exclude,
    )
    return _options_payload(challenge, options, user_id=user_id, kind="register")


def registration_verify(
    token: str,
    ip: str,
    *,
    challenge_id: str,
    credential: dict[str, Any],
    nickname: str,
) -> dict[str, Any] | PasskeyError | PasskeyRejected:
    label = nickname.strip()[:80]
    if not label:
        return "invalid"
    settings = get_settings()
    with session_scope() as db:
        found = _load_live_session(db, token, ip)
        if found is None:
            return "unauthenticated"
        user, row = found
        if not session_is_recent(row):
            return "stale"
        challenge = _take_challenge(db, challenge_id, kind="register", user_id=user.id)
        if challenge is None:
            return "invalid"
        try:
            verified = verify_registration_response(
                credential=_prepare_credential(credential),
                expected_challenge=base64url_to_bytes(challenge),
                expected_rp_id=settings.webauthn_rp_id,
                expected_origin=settings.public_url.rstrip("/"),
                require_user_verification=False,
            )
        except InvalidRegistrationResponse as exc:
            logger.warning("passkey registration rejected: %s", exc)
            return PasskeyRejected(str(exc))
        transports = credential.get("response", {}).get("transports")
        stored = WebAuthnCredential(
            id=bytes_to_base64url(verified.credential_id),
            user_id=user.id,
            public_key=bytes_to_base64url(verified.credential_public_key),
            sign_count=verified.sign_count,
            transports=transports if isinstance(transports, list) else [],
            aaguid=verified.aaguid,
            backup_eligible=verified.credential_device_type == CredentialDeviceType.MULTI_DEVICE,
            backup_state=verified.credential_backed_up,
            nickname=label,
            last_used_at=utcnow(),
        )
        db.add(stored)
        db.flush()
        add_event(
            db,
            type="auth.passkey_registered",
            actor_type="user",
            actor_id=user.id,
            payload={"nickname": label},
        )
        return _credential_public(stored)


def authentication_options() -> dict[str, Any]:
    settings = get_settings()
    challenge = secrets.token_bytes(32)
    options = generate_authentication_options(
        rp_id=settings.webauthn_rp_id,
        challenge=challenge,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    return _options_payload(challenge, options, user_id=None, kind="authenticate")


def authentication_verify(
    *,
    challenge_id: str,
    credential: dict[str, Any],
    ip: str,
    user_agent: str,
    existing_token: str | None,
) -> AuthSession | PasskeyStepUp | Literal["invalid"]:
    settings = get_settings()
    with session_scope() as db:
        challenge = _take_challenge(db, challenge_id, kind="authenticate", user_id=None)
        if challenge is None:
            return "invalid"
        credential = _prepare_credential(credential)
        cred_id = credential.get("id")
        if not isinstance(cred_id, str):
            return "invalid"
        stored = db.get(WebAuthnCredential, cred_id)
        if stored is None:
            return "invalid"
        try:
            verified = verify_authentication_response(
                credential=credential,
                expected_challenge=base64url_to_bytes(challenge),
                expected_rp_id=settings.webauthn_rp_id,
                expected_origin=settings.public_url.rstrip("/"),
                credential_public_key=base64url_to_bytes(stored.public_key),
                credential_current_sign_count=stored.sign_count,
                require_user_verification=False,
            )
        except InvalidAuthenticationResponse:
            return "invalid"
        response = credential.get("response")
        handle = response.get("userHandle") if isinstance(response, dict) else None
        if isinstance(handle, str) and base64url_to_bytes(handle) != stored.user_id.encode():
            return "invalid"
        user = db.get(User, stored.user_id)
        if user is None or user.disabled_at is not None:
            return "invalid"
        stored.sign_count = verified.new_sign_count
        stored.last_used_at = utcnow()
        stored.backup_state = verified.credential_backed_up
        if existing_token:
            current = _load_live_session(db, existing_token, ip)
            if current is not None and current[0].id == user.id:
                current[1].reauthenticated_at = utcnow()
                current[1].auth_method = "passkey"
                add_event(
                    db,
                    type="auth.passkey_step_up",
                    actor_type="user",
                    actor_id=user.id,
                    payload={},
                )
                return PasskeyStepUp(user_public(user))
        raw, expires_at = _issue_session(
            db,
            user,
            ip=ip,
            user_agent=user_agent,
            trust_device=False,
            auth_method="passkey",
            device_label=stored.nickname,
        )
        add_event(
            db,
            type="auth.login",
            actor_type="user",
            actor_id=user.id,
            payload={"method": "passkey"},
        )
        return AuthSession(token=raw, user=user_public(user), expires_at=expires_at)


def list_credentials(token: str, ip: str) -> list[dict[str, Any]] | None:
    with session_scope() as db:
        found = _load_live_session(db, token, ip)
        if found is None:
            return None
        user, _row = found
        rows = db.scalars(
            select(WebAuthnCredential)
            .where(WebAuthnCredential.user_id == user.id)
            .order_by(WebAuthnCredential.created_at.desc())
        ).all()
        return [_credential_public(item) for item in rows]


def rename_credential(
    token: str, ip: str, credential_id: str, nickname: str
) -> dict[str, Any] | PasskeyError:
    label = nickname.strip()[:80]
    if not label:
        return "invalid"
    with session_scope() as db:
        found = _load_live_session(db, token, ip)
        if found is None:
            return "unauthenticated"
        user, row = found
        if not session_is_recent(row):
            return "stale"
        stored = db.get(WebAuthnCredential, credential_id)
        if stored is None or stored.user_id != user.id:
            return "missing"
        stored.nickname = label
        add_event(
            db,
            type="auth.passkey_renamed",
            actor_type="user",
            actor_id=user.id,
            payload={"credential_id": credential_id},
        )
        return _credential_public(stored)


def delete_credential(token: str, ip: str, credential_id: str) -> PasskeyError | Literal["ok"]:
    with session_scope() as db:
        found = _load_live_session(db, token, ip)
        if found is None:
            return "unauthenticated"
        user, row = found
        if not session_is_recent(row):
            return "stale"
        stored = db.get(WebAuthnCredential, credential_id)
        if stored is None or stored.user_id != user.id:
            return "missing"
        count = db.scalar(
            select(func.count())
            .select_from(WebAuthnCredential)
            .where(WebAuthnCredential.user_id == user.id)
        )
        if user.password_hash is None and (count or 0) <= 1:
            return "last"
        db.delete(stored)
        add_event(
            db,
            type="auth.passkey_deleted",
            actor_type="user",
            actor_id=user.id,
            payload={"credential_id": credential_id},
        )
        return "ok"


def _take_challenge(
    db: Any,
    challenge_id: str,
    *,
    kind: str,
    user_id: str | None,
) -> str | None:
    row = db.get(WebAuthnChallenge, challenge_id)
    if row is None or row.kind != kind or as_utc(row.expires_at) <= utcnow():
        return None
    if user_id is not None and row.user_id != user_id:
        return None
    challenge = row.challenge
    db.delete(row)
    return str(challenge)


def _credential_public(row: WebAuthnCredential) -> dict[str, Any]:
    return {
        "id": row.id,
        "nickname": row.nickname,
        "aaguid": row.aaguid,
        "transports": row.transports,
        "backup_eligible": row.backup_eligible,
        "backup_state": row.backup_state,
        "sign_count": row.sign_count,
        "created_at": as_utc(row.created_at).isoformat(),
        "last_used_at": as_utc(row.last_used_at).isoformat() if row.last_used_at else None,
    }
