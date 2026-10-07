from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

YES_NO = {"yes", "no", "unknown"}


class AmenityFlags(BaseModel):
    model_config = ConfigDict(extra="forbid")

    laundry: str | None = None
    doorman: str | None = None
    elevator: str | None = None
    outdoor: str | None = None
    gym: str | None = None

    def cleaned(self) -> dict[str, str] | str:
        data = self.model_dump(exclude_none=True)
        if "laundry" in data and data["laundry"] not in {"in_unit", "building", "no"}:
            return "invalid"
        for key in ("doorman", "elevator", "outdoor", "gym"):
            if key in data and data[key] not in YES_NO:
                return "invalid"
        return data


class NycAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subway: str | None = None
    commute_lines: list[str] | None = None
    commute_gct_minutes: int | None = None
    east_side_access: str | None = None
    is_roosevelt_island: bool | None = None
    budget_band: str | None = None
    kitchen_status: str | None = None
    amenities: list[str] | None = None
    amenity_flags: AmenityFlags | None = None
    building_year: int | None = None
    newer_building: bool | None = None
    furnished: bool | None = None
    short_term: bool | None = None
    sublet: bool | None = None
    verified: bool | None = None
    ready: bool | None = None

    def cleaned(self) -> dict[str, Any] | str:
        if self.east_side_access and self.east_side_access not in {
            "strong",
            "ok",
            "weak",
            "unverified",
        }:
            return "invalid"
        if self.budget_band and self.budget_band not in {"standard_≤3000", "ri_stretch_≤4000"}:
            return "invalid"
        if self.kitchen_status and self.kitchen_status not in {
            "ok",
            "unverified",
            "small",
            "old",
            "unknown",
        }:
            return "invalid"
        flags: dict[str, str] = {}
        if self.amenity_flags is not None:
            parsed = self.amenity_flags.cleaned()
            if isinstance(parsed, str):
                return parsed
            flags = parsed
        data = self.model_dump(exclude_none=True)
        if flags:
            data["amenity_flags"] = flags
        elif "amenity_flags" in data:
            data.pop("amenity_flags")
        return data


class TxAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    list_price: float | None = None
    hoa_monthly: float | None = None
    tax_annual: float | None = None
    est_rent: float | None = None
    cap_rate: float | None = None
    lot_sqft: float | None = None
    year_built: int | None = None
    property_type: str | None = None
    school_rating: float | None = None
    flood_zone: str | None = Field(default=None)
    verified: bool | None = None
    ready: bool | None = None

    def cleaned(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


def validate_attrs(schema_id: str, raw: object) -> dict[str, Any] | str:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        return "invalid"
    try:
        if schema_id == "nyc-rental-v1":
            return NycAttrs.model_validate(raw).cleaned()
        if schema_id == "tx-purchase-v1":
            return TxAttrs.model_validate(raw).cleaned()
    except ValidationError:
        return "invalid"
    return "invalid"
