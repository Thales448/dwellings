from sqlalchemy import select
from tests.test_auth import PASSWORD, Client

from app.core.db import session_scope
from app.jobs.models import Job
from app.listings.stream import hub


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
    if created.status_code != 200:
        signed = client.post(
            "/api/v1/auth/password/login",
            {"email": "admin@example.com", "password": PASSWORD},
        )
        assert signed.status_code == 200, signed.text
    return client


def _hunt(client: Client) -> str:
    created = client.post(
        "/api/v1/hunts",
        {
            "name": "NYC · Couple",
            "slug": "nyc-core",
            "kind": "rental",
            "schema": "nyc-rental-v1",
            "criteria": {"price_ceiling": 3000, "ri_price_ceiling": 4000},
            "rating_scale": 5,
        },
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _body(hunt_id: str, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "hunt_id": hunt_id,
        "external_id": "cl-1",
        "url": "https://www.streeteasy.com/building/sunnyside?utm_source=digest",
        "source": "streeteasy",
        "title": "Elevator one-bed by the 7",
        "listing_type": "couple",
        "unit_kind": "full_1br",
        "beds": "1BR",
        "price": 2800,
        "neighborhood": "Sunnyside",
        "geo_bucket": "sunnyside",
        "scam_risk_agent": "low",
        "attrs": {"subway": "7", "is_roosevelt_island": False},
    }
    body.update(overrides)
    return body


def test_upsert_status_never_delete_and_presentable() -> None:
    admin = _admin()
    hunt_id = _hunt(admin)
    mailbox = hub.subscribe()
    try:
        created = admin.post("/api/v1/listings", _body(hunt_id))
        assert created.status_code == 201, created.text
        listing = created.json()["listing"]
        assert created.json()["duplicate"] is False
        assert listing["short_id"] == 1
        assert listing["beds"] == 1
        assert listing["beds_label"] == "1br"
        assert listing["url"] == "https://streeteasy.com/building/sunnyside"
        assert listing["source_snapshot"] == {
            "title": "Elevator one-bed by the 7",
            "price": 2800,
        }
        assert listing["is_presentable"] is True
        assert listing["scam_risk"] == "low"
        event = mailbox.get(timeout=2)
        assert event["type"] == "listing.created"

        again = admin.post(
            "/api/v1/listings",
            _body(
                hunt_id,
                url="https://streeteasy.com/building/sunnyside/",
                title="Quieter one-bed",
            ),
        )
        assert again.status_code == 200, again.text
        assert again.json()["duplicate"] is True
        assert again.json()["listing"]["id"] == listing["id"]
        assert again.json()["listing"]["short_id"] == 1
        assert again.json()["listing"]["source_snapshot"]["title"] == "Elevator one-bed by the 7"

        second = admin.post(
            "/api/v1/listings",
            _body(
                hunt_id,
                external_id="cl-2",
                url="https://streeteasy.com/building/other",
                price=3500,
            ),
        )
        assert second.status_code == 201, second.text
        assert second.json()["listing"]["short_id"] == 2
        assert second.json()["listing"]["is_presentable"] is False

        island = admin.post(
            "/api/v1/listings",
            _body(
                hunt_id,
                external_id="cl-ri",
                url="https://streeteasy.com/building/ri",
                price=3800,
                attrs={"is_roosevelt_island": True, "budget_band": "ri_stretch_≤4000"},
            ),
        )
        assert island.status_code == 201, island.text
        assert island.json()["listing"]["is_presentable"] is True

        hidden = admin.get(f"/api/v1/listings?hunt_id={hunt_id}")
        assert hidden.status_code == 200
        shown = {item["external_id"] for item in hidden.json()["listings"]}
        assert "cl-2" not in shown
        assert {"cl-1", "cl-ri"} <= shown
        everything = admin.get(f"/api/v1/listings?hunt_id={hunt_id}&presentable=false")
        assert "cl-2" in {item["external_id"] for item in everything.json()["listings"]}

        page = admin.get(f"/api/v1/listings?hunt_id={hunt_id}&limit=1")
        assert page.json()["next_cursor"]
        nxt = admin.get(
            f"/api/v1/listings?hunt_id={hunt_id}&limit=1&cursor={page.json()['next_cursor']}"
        )
        assert nxt.status_code == 200
        assert nxt.json()["listings"][0]["id"] != page.json()["listings"][0]["id"]

        by_short = admin.get(f"/api/v1/listings/%231?hunt_id={hunt_id}")
        assert by_short.status_code == 200, by_short.text
        assert by_short.json()["short_id"] == 1

        missing_reason = admin.post(
            f"/api/v1/listings/{listing['id']}/status",
            {"status": "demoted"},
        )
        assert missing_reason.status_code == 400
        demoted = admin.post(
            f"/api/v1/listings/{listing['id']}/status",
            {"status": "demoted", "demotion_reason": "bait"},
        )
        assert demoted.status_code == 200, demoted.text
        assert demoted.json()["listing"]["is_presentable"] is False

        checked = admin.post(f"/api/v1/listings/{listing['id']}/checked", {})
        assert checked.status_code == 200, checked.text
        assert checked.json()["listing"]["availability_checked_at"]

        removed = admin.delete(f"/api/v1/listings/{listing['id']}")
        assert removed.status_code == 200, removed.text
        kept = admin.get(f"/api/v1/listings/{listing['id']}")
        assert kept.status_code == 200
        assert kept.json()["status"] == "dead"
        assert kept.json()["unavailable_date"]
        assert kept.json()["is_presentable"] is False

        outsider = Client()
        invited = admin.post(
            "/api/v1/auth/invites",
            {"role": "owner", "email": "outsider-listings@example.com"},
        )
        assert invited.status_code == 201, invited.text
        assert (
            outsider.post(
                "/api/v1/auth/invite/accept",
                {
                    "token": invited.json()["token"],
                    "email": "outsider-listings@example.com",
                    "password": PASSWORD,
                    "display_name": "Outsider",
                },
            ).status_code
            == 200
        )
        assert outsider.get(f"/api/v1/listings/{listing['id']}").status_code == 404
        blocked = outsider.delete(f"/api/v1/listings/{listing['id']}?hard=true")
        assert blocked.status_code == 404

        gone = admin.delete(f"/api/v1/listings/{second.json()['listing']['id']}?hard=true")
        assert gone.status_code == 200, gone.text
        assert admin.get(f"/api/v1/listings/{second.json()['listing']['id']}").status_code == 404

        bulk = admin.post(
            "/api/v1/listings/bulk",
            {
                "hunt_id": hunt_id,
                "listings": [
                    _body(hunt_id, external_id="cl-3", url="https://example.com/a"),
                    {"title": ""},
                ],
            },
        )
        assert bulk.status_code == 200, bulk.text
        assert bulk.json()["results"][0]["ok"] is True
        assert bulk.json()["results"][1]["ok"] is False
    finally:
        hub.unsubscribe(mailbox)

    with session_scope() as db:
        kinds = set(db.scalars(select(Job.kind).where(Job.done_at.is_(None))).all())
    assert {"photo", "scam"} <= kinds
