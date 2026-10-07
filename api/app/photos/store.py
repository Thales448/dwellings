import hashlib
import io
from pathlib import Path
from uuid import uuid4

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.listings.models import Listing
from app.photos.models import Photo

SIZES = (480, 1280)
Image.MAX_IMAGE_PIXELS = 24_000_000


def photo_file(hunt_id: str, listing_id: str, sha: str, size: int) -> Path:
    root = get_settings().data_dir / "photos" / hunt_id / listing_id
    return root / f"{sha}_{size}.webp"


def _phash(image: Image.Image) -> str:
    small = image.convert("L").resize((8, 8))
    pixels = list(small.get_flattened_data())
    average = sum(pixels) / len(pixels)
    bits = 0
    for index, pixel in enumerate(pixels):
        if pixel >= average:
            bits |= 1 << index
    return f"{bits:016x}"


def _resize(image: Image.Image, size: int) -> Image.Image:
    copy = image.copy()
    copy.thumbnail((size, size))
    if copy.mode != "RGB":
        copy = copy.convert("RGB")
    return copy


def keep_image(
    db: Session,
    listing: Listing,
    data: bytes,
    *,
    original_url: str | None,
    caption: str | None,
    shows_kitchen: bool | None,
    origin: str,
) -> bool:
    existing = db.scalar(
        select(func.count()).select_from(Photo).where(Photo.listing_id == listing.id)
    )
    if int(existing or 0) >= get_settings().photo_max_per_listing:
        return False
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception:
        return False
    sha = hashlib.sha256(data).hexdigest()
    if (
        db.scalar(select(Photo).where(Photo.listing_id == listing.id, Photo.sha256 == sha))
        is not None
    ):
        return False
    rgb = image.convert("RGB")
    digest = _phash(rgb)
    width, height = rgb.size
    for size in SIZES:
        path = photo_file(listing.hunt_id, listing.id, sha, size)
        path.parent.mkdir(parents=True, exist_ok=True)
        _resize(rgb, size).save(path, format="WEBP", quality=80)
    position = int(
        db.scalar(select(func.max(Photo.position)).where(Photo.listing_id == listing.id)) or 0
    )
    cover = (
        db.scalar(select(Photo).where(Photo.listing_id == listing.id, Photo.is_cover.is_(True)))
        is None
    )
    db.add(
        Photo(
            id=str(uuid4()),
            listing_id=listing.id,
            position=position + 1,
            origin=origin,
            original_url=original_url[:1000] if original_url else None,
            sha256=sha,
            phash=digest,
            width=width,
            height=height,
            caption=caption[:200] if caption else None,
            is_cover=cover,
            shows_kitchen=shows_kitchen,
        )
    )
    db.flush()
    return True
