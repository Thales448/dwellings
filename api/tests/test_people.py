from fastapi.testclient import TestClient
from tests.test_auth import PASSWORD, Client
from tests.test_listings import _body

from app.main import app

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
    if created.status_code != 200:
        signed = client.post(
            "/api/v1/auth/password/login",
            {"email": "admin@example.com", "password": PASSWORD},
        )
        assert signed.status_code == 200, signed.text
    return client


def _hunt(client: Client, slug: str, name: str) -> str:
    created = client.post(
        "/api/v1/hunts",
        {
            "name": name,
            "slug": slug,
            "kind": "rental",
            "schema": "nyc-rental-v1",
            "criteria": {"price_ceiling": 3000},
            "rating_scale": 5,
        },
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _pair(admin: Client, hunt_id: str, name: str) -> tuple[str, str]:
    issued = admin.post(f"/api/v1/hunts/{hunt_id}/pairing-codes", {})
    assert issued.status_code == 201, issued.text
    paired = Client().post("/api/v1/agents/pair", {"code": issued.json()["code"], "name": name})
    assert paired.status_code == 201, paired.text
    body = paired.json()
    return str(body["token"]), str(body["agent_id"])


def _post(token: str, body: dict[str, object]) -> None:
    http = TestClient(app, base_url=ORIGIN)
    created = http.post(
        "/api/v1/listings",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 201, created.text


def test_admin_chooses_feeds_and_agents() -> None:
    admin = _admin()
    nyc = _hunt(admin, "nyc-people", "NYC people")
    austin = _hunt(admin, "austin-people", "Austin people")
    east_token, east_id = _pair(admin, nyc, "east-agent")
    west_token, west_id = _pair(admin, nyc, "west-agent")
    _post(
        east_token,
        _body(nyc, external_id="east-1", title="East one-bed", url="https://east.example/1"),
    )
    _post(
        west_token,
        _body(nyc, external_id="west-1", title="West one-bed", url="https://west.example/1"),
    )

    outsider = Client()
    assert outsider.get("/api/v1/admin/users").status_code == 401

    created = admin.post(
        "/api/v1/admin/users",
        {
            "email": "guest@example.com",
            "display_name": "Guest",
            "password": PASSWORD,
            "grants": [
                {"hunt_id": nyc, "role": "viewer", "agent_ids": [east_id]},
            ],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["grants"], created.text
    assert created.json()["grants"][0]["agent_ids"] == [east_id]

    guest = Client()
    assert (
        guest.post(
            "/api/v1/auth/password/login",
            {"email": "guest@example.com", "password": PASSWORD},
        ).status_code
        == 200
    )
    assert guest.get("/api/v1/admin/feeds").status_code == 403
    hunts = guest.get("/api/v1/hunts")
    assert hunts.status_code == 200
    assert [hunt["id"] for hunt in hunts.json()["hunts"]] == [nyc]
    assert guest.get(f"/api/v1/hunts/{austin}").status_code == 404

    listed = guest.get(f"/api/v1/listings?hunt_id={nyc}&presentable=false")
    assert listed.status_code == 200, listed.text
    titles = [row["title"] for row in listed.json()["listings"]]
    assert titles == ["East one-bed"]
    agents = guest.get(f"/api/v1/hunts/{nyc}/agents")
    assert agents.status_code == 200
    assert [agent["id"] for agent in agents.json()["agents"]] == [east_id]

    hidden = admin.get(f"/api/v1/listings?hunt_id={nyc}&presentable=false")
    west = next(row for row in hidden.json()["listings"] if row["title"] == "West one-bed")
    assert guest.get(f"/api/v1/listings/{west['id']}").status_code == 404

    opened = admin.put(
        f"/api/v1/admin/users/{created.json()['id']}/access",
        {"grants": [{"hunt_id": nyc, "role": "rater", "agent_ids": None}]},
    )
    assert opened.status_code == 200, opened.text
    assert opened.json()["grants"][0]["agent_ids"] is None
    again = guest.get(f"/api/v1/listings?hunt_id={nyc}&presentable=false")
    assert {row["title"] for row in again.json()["listings"]} == {"East one-bed", "West one-bed"}
    assert west_id
