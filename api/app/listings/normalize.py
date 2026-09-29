from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING = {"fbclid", "gclid"}
STATUSES = {"new", "alive", "watching", "dead", "rented", "scam", "demoted"}
LISTING_TYPES = {"couple", "roommate", "room"}
UNIT_KINDS = {"full_studio", "full_1br", "full_2br_plus", "room", "multi", "unknown"}
ADDRESS_PRECISION = {"exact", "street", "area"}
HONESTY = {
    "bait_pricing",
    "title_beds_mismatch",
    "short_term",
    "sublet",
    "furnished",
    "rent_stabilized_claim",
    "kitchen_unverified",
    "provisional_ri",
    "soft_address",
    "broker_fee_unclear",
}
DEMOTION = {"room", "2br", "bait", "dup", "out_of_geo", "basement", "other"}
SCAM = {"low", "medium", "high"}
ACTIVE = {"new", "alive", "watching"}


def normalize_url(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    parts = urlsplit(raw.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return None
    host = parts.hostname.lower()
    if host.startswith("www."):
        host = host[4:]
    if parts.port:
        host = f"{host}:{parts.port}"
    path = parts.path.rstrip("/") or "/"
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING
    ]
    query.sort()
    return urlunsplit((parts.scheme.lower(), host, path, urlencode(query), ""))


def normalize_beds(raw: object) -> tuple[float, str] | None:
    text = str(raw).strip().lower().replace(" ", "")
    if text.endswith("br"):
        text = text[:-2]
    try:
        beds = float(text)
    except ValueError:
        return None
    if beds < 0 or beds > 20:
        return None
    if beds == int(beds):
        whole = int(beds)
        label = "studio" if whole == 0 else f"{whole}br"
        return float(whole), label
    return beds, str(beds)
