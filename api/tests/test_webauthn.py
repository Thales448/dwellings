from datetime import timedelta

from sqlalchemy import select
from tests.test_auth import PASSWORD, Client
from tests.virtual_authenticator import VirtualAuthenticator
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url, encode_cbor, parse_cbor

from app.auth.models import SessionRow, User, WebAuthnCredential
from app.auth.passkeys import _prepare_credential
from app.core.clock import utcnow
from app.core.db import session_scope

RP_ID = "dwellings.rtech.cloud"
ORIGIN = "https://dwellings.rtech.cloud"


def _admin() -> Client:
    client = Client()
    created = client.post(
        "/api/v1/setup",
        {
            "token": "bootstrap-token-value",
            "email": "admin@example.com",
            "password": PASSWORD,
            "display_name": "Orpheus",
        },
    )
    if created.status_code == 404:
        assert (
            client.post(
                "/api/v1/auth/password/login",
                {"email": "admin@example.com", "password": PASSWORD},
            ).status_code
            == 200
        )
    else:
        assert created.status_code == 200
    return client


def _register(client: Client, authenticator: VirtualAuthenticator, nickname: str) -> str:
    options = client.post("/api/v1/auth/passkey/register/options", {})
    assert options.status_code == 200, options.text
    body = options.json()
    credential = authenticator.registration(
        challenge=body["options"]["challenge"],
        origin=ORIGIN,
        rp_id=RP_ID,
    )
    verified = client.post(
        "/api/v1/auth/passkey/register/verify",
        {
            "challenge_id": body["challenge_id"],
            "credential": credential,
            "nickname": nickname,
        },
    )
    assert verified.status_code == 201, verified.text
    return str(verified.json()["id"])


def test_phone_attestation_is_ignored() -> None:
    auth_data = b"\x00" * 37
    packed = bytes_to_base64url(
        encode_cbor({"fmt": "packed", "attStmt": {"sig": b"abc"}, "authData": auth_data})
    )
    prepared = _prepare_credential(
        {"id": "aa==", "rawId": "aa", "response": {"attestationObject": packed}}
    )
    decoded = parse_cbor(base64url_to_bytes(prepared["response"]["attestationObject"]))
    assert prepared["id"] == bytes_to_base64url(base64url_to_bytes("aa=="))
    assert decoded["fmt"] == "none"
    assert decoded["attStmt"] == {}
    assert decoded["authData"] == auth_data


def test_registration_options_ask_iphone_for_face_id() -> None:
    client = _admin()
    options = client.post("/api/v1/auth/passkey/register/options", {})
    assert options.status_code == 200, options.text
    body = options.json()["options"]
    selection = body["authenticatorSelection"]
    assert selection["authenticatorAttachment"] == "platform"
    assert selection["residentKey"] == "required"
    assert selection["requireResidentKey"] is True
    assert selection["userVerification"] == "preferred"
    assert body["attestation"] == "none"
    algorithms = {item["alg"] for item in body["pubKeyCredParams"]}
    assert -7 in algorithms
    assert -257 in algorithms


def test_virtual_authenticator_registers_and_signs_in() -> None:
    client = _admin()
    user_id = client.get("/api/v1/auth/sessions")
    assert user_id.status_code == 200
    with session_scope() as db:
        rows = db.scalars(select(SessionRow).where(SessionRow.revoked_at.is_(None))).all()
        for row in rows:
            row.reauthenticated_at = utcnow() - timedelta(minutes=11)
    stale = client.post("/api/v1/auth/passkey/register/options", {})
    assert stale.status_code == 403
    assert stale.json()["code"] == "step_up_needed"

    fresh = Client()
    assert (
        fresh.post(
            "/api/v1/auth/password/login",
            {"email": "admin@example.com", "password": PASSWORD},
        ).status_code
        == 200
    )
    phone = VirtualAuthenticator()
    first_id = _register(fresh, phone, "iPhone · Face ID")
    listed = fresh.get("/api/v1/auth/credentials")
    assert listed.status_code == 200
    assert listed.json()["credentials"][0]["nickname"] == "iPhone · Face ID"

    renamed = fresh.patch(
        f"/api/v1/auth/credentials/{first_id}",
        {"nickname": "Laptop · Touch ID"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["nickname"] == "Laptop · Touch ID"

    assert fresh.post("/api/v1/auth/sessions/revoke-all", {}).status_code == 200
    anon = Client()
    options = anon.post("/api/v1/auth/passkey/options", {})
    assert options.status_code == 200
    challenge = options.json()
    with session_scope() as db:
        owner = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert owner is not None
        handle = owner.id.encode()
    assertion = phone.authentication(
        challenge=challenge["options"]["challenge"],
        origin=ORIGIN,
        rp_id=RP_ID,
        user_handle=handle,
    )
    signed_in = anon.post(
        "/api/v1/auth/passkey/verify",
        {"challenge_id": challenge["challenge_id"], "credential": assertion},
    )
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json()["email"] == "admin@example.com"

    again = anon.post("/api/v1/auth/passkey/options", {})
    second = phone.authentication(
        challenge=again.json()["options"]["challenge"],
        origin=ORIGIN,
        rp_id=RP_ID,
        user_handle=handle,
    )
    with session_scope() as db:
        stored = db.get(WebAuthnCredential, first_id)
        assert stored is not None
        stored.sign_count = phone.sign_count
    replay = anon.post(
        "/api/v1/auth/passkey/verify",
        {"challenge_id": again.json()["challenge_id"], "credential": second},
    )
    assert replay.status_code == 400

    removed = anon.delete(f"/api/v1/auth/credentials/{first_id}")
    assert removed.status_code == 200
    _register(anon, phone, "iPhone · Face ID")
    with session_scope() as db:
        owner = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert owner is not None
        owner.password_hash = None
    blocked = anon.delete(f"/api/v1/auth/credentials/{first_id}")
    assert blocked.status_code == 409

    laptop = VirtualAuthenticator()
    second_id = _register(anon, laptop, "Laptop · Touch ID")
    assert anon.delete(f"/api/v1/auth/credentials/{first_id}").status_code == 200
    assert anon.delete(f"/api/v1/auth/credentials/{second_id}").status_code == 409
