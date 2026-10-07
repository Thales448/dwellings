from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.photos.models import Photo


def photo_public(row: Photo) -> dict[str, Any]:
    return {
        "id": row.id,
        "position": row.position,
        "caption": row.caption,
        "is_cover": row.is_cover,
        "width": row.width,
        "height": row.height,
        "shows_kitchen": row.shows_kitchen,
        "url": f"/api/v1/photos/{row.id}/1280",
        "thumb": f"/api/v1/photos/{row.id}/480",
    }


def photos_by_listing(db: Session, listing_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not listing_ids:
        return {}
    rows = db.scalars(
        select(Photo).where(Photo.listing_id.in_(listing_ids)).order_by(Photo.position.asc())
    ).all()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row.listing_id].append(photo_public(row))
    return grouped
