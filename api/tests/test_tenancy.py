from tests.test_auth import PASSWORD, Client


def _login(email: str) -> Client:
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
    if email == "admin@example.com" and created.status_code == 200:
        return client
    signed = client.post(
        "/api/v1/auth/password/login",
        {"email": email, "password": PASSWORD},
    )
    assert signed.status_code == 200, signed.text
    return client


def test_hunts_are_isolated() -> None:
    admin = _login("admin@example.com")
    nyc = admin.post(
        "/api/v1/hunts",
        {
            "name": "NYC · Couple",
            "slug": "nyc-couple",
            "kind": "rental",
            "schema": "nyc-rental-v1",
            "criteria": {"price_ceiling": 3000},
            "rating_scale": 5,
            "rating_weights": {"orpheus": 0.5, "partner": 0.5},
        },
    )
    assert nyc.status_code == 201, nyc.text
    nyc_id = nyc.json()["id"]

    invited = admin.post(
        f"/api/v1/hunts/{nyc_id}/invites",
        {"role": "viewer", "email": "viewer@example.com"},
    )
    assert invited.status_code == 201, invited.text
    viewer = Client()
    accepted = viewer.post(
        "/api/v1/auth/invite/accept",
        {
            "token": invited.json()["token"],
            "email": "viewer@example.com",
            "password": PASSWORD,
            "display_name": "Viewer",
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert viewer.get(f"/api/v1/hunts/{nyc_id}").status_code == 200
    assert viewer.patch(
        f"/api/v1/hunts/{nyc_id}",
        {"criteria": {"price_ceiling": 1}},
    ).status_code == 403

    owner_invite = admin.post(
        "/api/v1/auth/invites",
        {"role": "owner", "email": "texan@example.com"},
    )
    assert owner_invite.status_code == 201, owner_invite.text
    partner = Client()
    assert (
        partner.post(
            "/api/v1/auth/invite/accept",
            {
                "token": owner_invite.json()["token"],
                "email": "texan@example.com",
                "password": PASSWORD,
                "display_name": "Texan",
            },
        ).status_code
        == 200
    )
    texas = partner.post(
        "/api/v1/hunts",
        {
            "name": "Texas · Investment",
            "slug": "texas-investment",
            "kind": "purchase",
            "schema": "tx-purchase-v1",
            "rating_scale": 10,
        },
    )
    assert texas.status_code == 201, texas.text
    texas_id = texas.json()["id"]

    assert partner.get(f"/api/v1/hunts/{nyc_id}").status_code == 404
    assert partner.patch(f"/api/v1/hunts/{nyc_id}", {"name": "Nope"}).status_code == 404
    assert admin.get(f"/api/v1/hunts/{texas_id}").status_code == 404
    assert admin.post(
        f"/api/v1/hunts/{texas_id}/invites",
        {"role": "rater", "email": "spy@example.com"},
    ).status_code == 404

    mine = partner.get("/api/v1/hunts")
    assert mine.status_code == 200
    slugs = {item["slug"] for item in mine.json()["hunts"]}
    assert slugs == {"texas-investment"}
    me = partner.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["hunts"][0]["slug"] == "texas-investment"
