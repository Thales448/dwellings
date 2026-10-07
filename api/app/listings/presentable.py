from app.listings.craigslist import is_posting_url
from app.listings.models import Listing
from app.listings.normalize import ACTIVE
from app.tenancy.models import Hunt

STUDIO_1BR_KINDS = frozenset({"full_studio", "full_1br"})
COUPLE_PRESENTABLE_KINDS = frozenset({"full_studio", "full_1br", "full_2br_plus"})


def presentable(hunt: Hunt, listing: Listing) -> bool:
    if listing.status not in ACTIVE or listing.demoted or listing.scam_risk == "high":
        return False
    if listing.unavailable_date is not None:
        return False
    if hunt.schema_id != "nyc-rental-v1":
        return True
    if not is_posting_url(listing.url) or not listing.link_ok:
        return False
    if listing.listing_type != "couple" or listing.unit_kind not in COUPLE_PRESENTABLE_KINDS:
        return False
    if listing.geo_bucket == "out_of_scope":
        return False
    criteria = hunt.criteria or {}
    ceiling = float(criteria.get("price_ceiling", 3000))
    ceiling_2br = float(criteria.get("price_ceiling_2br", 3200))
    ri_ceiling = float(criteria.get("ri_price_ceiling", 4000))
    on_island = bool((listing.attrs or {}).get("is_roosevelt_island"))
    price = float(listing.price)

    # Couple 2BR+: hard ceiling only — never apply the RI studio/1BR stretch.
    if listing.unit_kind == "full_2br_plus":
        return price <= ceiling_2br

    # Studio / 1BR: general ceiling, with optional Roosevelt Island stretch.
    if price <= ceiling:
        return True
    return on_island and price <= ri_ceiling
