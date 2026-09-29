from app.listings.models import Listing
from app.listings.normalize import ACTIVE
from app.tenancy.models import Hunt


def presentable(hunt: Hunt, listing: Listing) -> bool:
    if listing.status not in ACTIVE or listing.demoted or listing.scam_risk == "high":
        return False
    if listing.unavailable_date is not None:
        return False
    if hunt.schema_id != "nyc-rental-v1":
        return True
    if listing.listing_type != "couple" or listing.unit_kind not in {"full_studio", "full_1br"}:
        return False
    if listing.geo_bucket == "out_of_scope":
        return False
    criteria = hunt.criteria or {}
    ceiling = float(criteria.get("price_ceiling", 3000))
    ri_ceiling = float(criteria.get("ri_price_ceiling", 4000))
    on_island = bool((listing.attrs or {}).get("is_roosevelt_island"))
    if listing.price <= ceiling:
        return True
    return on_island and listing.price <= ri_ceiling
