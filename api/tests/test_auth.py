import time
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models import SessionRow, User
from app.auth.passwords import dummy_verify, verify_password
from app.auth.service import issue_recovery_link
from app.core.clock import utcnow
from app.core.db import session_scope
from app.main import app

ORIGIN = "https://dwellings.rtech.cloud"
PASSWORD = "correct-horse-staple-dwellings"


class Client:
    def __init__(self, forwarded_for: str | None = None) -> None:
        self.http = TestClient(app, base_url=ORIGIN)
        self.forwarded_for = forwarded_for
        self.csrf: str | None = None

    def _csrf_headers(self) -> dict[str, str]:
        if self.csrf is None:
            issued = self.http.get("/api/v1/csrf")
            assert issued.status_code == 200
            token = issued.json()["token"]
            assert isinstance(token, str)
            self.csrf = token
        headers = {"origin": ORIGIN, "x-csrf-token": self.csrf}
        if self.forwarded_for:
            headers["x-forwarded-for"] = self.forwarded_for
        return headers

    def post(self, path: str, body: dict[str, object]) -> TestClient:
        return self.http.post(path, json=body, headers=self._csrf_headers())  # type: ignore[return-value]

    def get(self, path: str) -> TestClient:
        headers: dict[str, str] = {}
        if self.forwarded_for:
            headers["x-forwarded-for"] = self.forwarded_for
        return self.http.get(path, headers=headers)  # type: ignore[return-value]

    def delete(self, path: str) -> TestClient:
        return self.http.delete(path, headers=self._csrf_headers())  # type: ignore[return-value]


@pytest.fixture(scope="module")
def admin_account() -> None:
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
    assert created.status_code == 200
    assert created.json()["is_admin"] is True
    closed = client.post(
        "/api/v1/setup",
        {
            "token": "bootstrap-token-value",
            "email": "admin@example.com",
            "password": PASSWORD,
            "display_name": "Orpheus",
        },
    )
    assert closed.status_code == 404


def test_sign_in_sign_out_and_revoke_sessions(admin_account: None) -> None:
    del admin_account
    first = Client()
    second = Client()
    assert (
        first.post(
            "/api/v1/auth/password/login",
            {"email": "admin@example.com", "password": PASSWORD, "trust_device": True},
        ).status_code
        == 200
    )
    assert (
        second.post(
            "/api/v1/auth/password/login",
            {"email": "admin@example.com", "password": PASSWORD},
        ).status_code
        == 200
    )

    mine = first.get("/api/v1/auth/sessions")
    assert mine.status_code == 200
    first_id = next(item["id"] for item in mine.json()["sessions"] if item["current"])
    assert any(item["trusted_until"] for item in mine.json()["sessions"])

    listed = second.get("/api/v1/auth/sessions")
    assert listed.status_code == 200
    assert len(listed.json()["sessions"]) >= 2
    assert second.delete(f"/api/v1/auth/sessions/{first_id}").status_code == 200
    assert first.get("/api/v1/auth/sessions").status_code == 401

    assert second.post("/api/v1/auth/sessions/revoke-others", {}).status_code == 200
    remaining = second.get("/api/v1/auth/sessions")
    assert remaining.status_code == 200
    assert len(remaining.json()["sessions"]) == 1
    current = remaining.json()["sessions"][0]
    assert current["current"] is True

    assert second.delete(f"/api/v1/auth/sessions/{current['id']}").status_code == 200
    assert second.get("/api/v1/auth/sessions").status_code == 401


def test_lockout_and_password_rules(admin_account: None, monkeypatch: pytest.MonkeyPatch) -> None:
    del admin_account
    admin = Client()
    assert (
        admin.post(
            "/api/v1/auth/password/login",
            {"email": "admin@example.com", "password": PASSWORD},
        ).status_code
        == 200
    )
    invited = admin.post(
        "/api/v1/auth/invites",
        {"role": "rater", "email": "partner@example.com"},
    )
    assert invited.status_code == 201
    partner = Client(forwarded_for="203.0.113.50")
    accepted = partner.post(
        "/api/v1/auth/invite/accept",
        {
            "token": invited.json()["token"],
            "email": "partner@example.com",
            "password": PASSWORD,
            "display_name": "Partner",
        },
    )
    assert accepted.status_code == 200

    common_invite = admin.post("/api/v1/auth/invites", {"role": "viewer"})
    assert common_invite.status_code == 201
    common = Client(forwarded_for="203.0.113.60").post(
        "/api/v1/auth/invite/accept",
        {
            "token": common_invite.json()["token"],
            "email": "common@example.com",
            "password": "123qweasdzxc",
            "display_name": "Common",
        },
    )
    assert common.status_code == 400
    assert "common" in common.json()["detail"]

    calls: list[str] = []
    real_verify = verify_password
    real_dummy = dummy_verify

    def counted_verify(password_hash: str, password: str) -> bool:
        calls.append("verify")
        return real_verify(password_hash, password)

    def counted_dummy(password: str) -> None:
        calls.append("dummy")
        real_dummy(password)

    monkeypatch.setattr("app.auth.service.verify_password", counted_verify)
    monkeypatch.setattr("app.auth.service.dummy_verify", counted_dummy)

    unknown = Client(forwarded_for="203.0.113.51")
    missing = unknown.post(
        "/api/v1/auth/password/login",
        {"email": "missing@example.com", "password": "not-the-password"},
    )
    assert missing.status_code == 401
    wrong = partner.post(
        "/api/v1/auth/password/login",
        {"email": "partner@example.com", "password": "not-the-password"},
    )
    assert wrong.status_code == 401
    assert "dummy" in calls and "verify" in calls

    locked = partner.post(
        "/api/v1/auth/password/login",
        {"email": "partner@example.com", "password": PASSWORD},
    )
    assert locked.status_code == 429
    assert locked.json()["code"] == "locked"
    time.sleep(1.2)
    assert (
        partner.post(
            "/api/v1/auth/password/login",
            {"email": "partner@example.com", "password": PASSWORD},
        ).status_code
        == 200
    )

    bare = TestClient(app, base_url=ORIGIN)
    rejected = bare.post(
        "/api/v1/auth/password/login",
        json={"email": "admin@example.com", "password": PASSWORD},
        headers={"origin": ORIGIN},
    )
    assert rejected.status_code == 403

    with session_scope() as db:
        user = db.scalar(select(User).where(User.email == "partner@example.com"))
        assert user is not None
        user.require_passkey = True
    stepped = Client(forwarded_for="203.0.113.54").post(
        "/api/v1/auth/password/login",
        {"email": "partner@example.com", "password": PASSWORD},
    )
    assert stepped.status_code == 401
    assert stepped.json()["code"] == "step_up_needed"
    with session_scope() as db:
        user = db.scalar(select(User).where(User.email == "partner@example.com"))
        assert user is not None
        user.require_passkey = False

    fresh = Client(forwarded_for="203.0.113.52")
    assert (
        fresh.post(
            "/api/v1/auth/password/login",
            {"email": "partner@example.com", "password": PASSWORD},
        ).status_code
        == 200
    )
    changed = fresh.post(
        "/api/v1/auth/password",
        {"password": "another-harbor-lantern-47", "current_password": PASSWORD},
    )
    assert changed.status_code == 200
    with session_scope() as db:
        user = db.scalar(select(User).where(User.email == "partner@example.com"))
        assert user is not None
        rows = db.scalars(select(SessionRow).where(SessionRow.user_id == user.id)).all()
        for row in rows:
            row.reauthenticated_at = utcnow() - timedelta(minutes=11)
    stale = fresh.post(
        "/api/v1/auth/password",
        {
            "password": "yet-another-harbor-lantern",
            "current_password": "another-harbor-lantern-47",
        },
    )
    assert stale.status_code == 403
    assert stale.json()["code"] == "step_up_needed"

    link = issue_recovery_link("partner@example.com")
    assert link is not None and link.startswith("https://dwellings.rtech.cloud/recover?token=")
    recovery_token = parse_qs(urlparse(link).query)["token"][0]
    recovered = fresh.post(
        "/api/v1/auth/recovery",
        {"token": recovery_token, "password": PASSWORD},
    )
    assert recovered.status_code == 200
    assert (
        Client(forwarded_for="203.0.113.53")
        .post(
            "/api/v1/auth/password/login",
            {"email": "partner@example.com", "password": PASSWORD},
        )
        .status_code
        == 200
    )
