"""Unit tests for nyc-rental-v1 presentable price bands (no HTTP)."""

from types import SimpleNamespace

from app.listings.presentable import presentable


def _hunt(**criteria):
    return SimpleNamespace(
        schema_id="nyc-rental-v1",
        criteria={
            "price_ceiling": 3000,
            "ri_price_ceiling": 4000,
            "price_ceiling_2br": 3200,
            **criteria,
        },
    )


def _listing(**overrides):
    base = {
        "status": "alive",
        "demoted": False,
        "scam_risk": "low",
        "unavailable_date": None,
        "url": "https://newyork.craigslist.org/brk/apa/d/brooklyn-test/7900000099.html",
        "link_ok": True,
        "listing_type": "couple",
        "unit_kind": "full_1br",
        "geo_bucket": "brooklyn",
        "price": 2800,
        "attrs": {},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_studio_1br_hard_ceiling() -> None:
    hunt = _hunt()
    assert presentable(hunt, _listing(unit_kind="full_studio", price=3000)) is True
    assert presentable(hunt, _listing(unit_kind="full_1br", price=3001)) is False


def test_ri_stretch_studio_1br_only() -> None:
    hunt = _hunt()
    ri = {"is_roosevelt_island": True}
    assert presentable(hunt, _listing(unit_kind="full_1br", price=4000, attrs=ri)) is True
    assert presentable(hunt, _listing(unit_kind="full_1br", price=4001, attrs=ri)) is False
    # 2BR must not get RI stretch
    assert (
        presentable(
            hunt,
            _listing(unit_kind="full_2br_plus", price=3500, attrs=ri),
        )
        is False
    )


def test_full_2br_plus_band() -> None:
    hunt = _hunt()
    assert presentable(hunt, _listing(unit_kind="full_2br_plus", price=3200)) is True
    assert presentable(hunt, _listing(unit_kind="full_2br_plus", price=3201)) is False
    assert presentable(hunt, _listing(unit_kind="full_2br_plus", price=3000)) is True
