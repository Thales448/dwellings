from tests.test_listings import _admin, _body

from app.core.db import session_scope
from app.listings.craigslist import judge, parse_posting
from app.listings.models import Listing
from app.listings.verify import store_check
from app.tenancy.models import Hunt

PAGE = """
<html><body>
<span id="titletextonly">Elevator one-bed by the 7</span>
<section id="postingbody">
<div class="print-information print-qrcode-container">QR Code Link to This Post</div>
Quiet walk-up with a real kitchen.
</section>
</body></html>
"""
GONE = """
<html><body>
<div class="removed">This posting has been deleted by its author.</div>
<span id="titletextonly">Elevator one-bed by the 7</span>
<section id="postingbody">Quiet walk-up with a real kitchen.</section>
</body></html>
"""
URL = "https://newyork.craigslist.org/que/apa/d/sunnyside-elevator/7900000099.html"


def test_posting_title_and_description_must_match() -> None:
    page = parse_posting(PAGE)
    assert page.title == "elevator one-bed by the 7"
    assert page.body == "quiet walk-up with a real kitchen."
    assert page.gone is False
    matched = judge(
        URL, "Elevator one-bed by the 7", "Quiet walk-up with a real kitchen.", page, None
    )
    assert matched[0]
    mismatch = judge(URL, "A different title", "Quiet walk-up with a real kitchen.", page, None)
    assert mismatch[0] is False
    assert mismatch[1] is not None
    assert "title does not match" in mismatch[1]
    wrong_notes = judge(URL, "Elevator one-bed by the 7", "Something else.", page, None)
    assert wrong_notes[0] is False
    assert wrong_notes[1] == "description does not match the Craigslist post"
    search = "https://newyork.craigslist.org/search/apa"
    assert judge(search, page.title, page.body, page, None)[1] == "not a craigslist posting link"
    assert parse_posting(GONE).gone is True
    assert judge(URL, page.title, page.body, parse_posting(GONE), None)[1] == (
        "the Craigslist post is gone"
    )


def test_checked_listing_stays_hidden_until_the_post_matches() -> None:
    admin = _admin()
    created_hunt = admin.post(
        "/api/v1/hunts",
        {
            "name": "Checked",
            "slug": "craigslist-check",
            "kind": "rental",
            "schema": "nyc-rental-v1",
            "criteria": {"price_ceiling": 3000},
            "rating_scale": 5,
        },
    )
    assert created_hunt.status_code == 201, created_hunt.text
    hunt_id = str(created_hunt.json()["id"])
    created = admin.post(
        "/api/v1/listings",
        _body(
            hunt_id,
            external_id="match-1",
            url=URL,
            notes="Quiet walk-up with a real kitchen.",
        ),
    )
    assert created.status_code == 201, created.text
    listing_id = created.json()["listing"]["id"]
    assert created.json()["listing"]["is_presentable"] is False
    with session_scope() as db:
        row = db.get(Listing, listing_id)
        hunt = db.get(Hunt, hunt_id)
        assert row is not None and hunt is not None
        store_check(row, hunt, parse_posting(PAGE), None)
    shown = admin.get(f"/api/v1/listings?hunt_id={hunt_id}")
    assert listing_id in {item["id"] for item in shown.json()["listings"]}
    with session_scope() as db:
        row = db.get(Listing, listing_id)
        hunt = db.get(Hunt, hunt_id)
        assert row is not None and hunt is not None
        row.notes = "A made-up description."
        store_check(row, hunt, parse_posting(PAGE), None)
    hidden = admin.get(f"/api/v1/listings?hunt_id={hunt_id}")
    assert listing_id not in {item["id"] for item in hidden.json()["listings"]}
    detail = admin.get(f"/api/v1/listings/{listing_id}")
    assert detail.json()["link_check"]["ok"] is False
    assert "description does not match" in detail.json()["link_check"]["error"]
