from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from app.core.config import get_settings
from app.core.db import session_scope
from app.core.security import client_ip
from app.listings.models import Listing
from app.listings.service import _actor, _listing_visible, _open_hunt
from app.photos.models import Photo
from app.photos.store import photo_file

router = APIRouter(prefix="/api/v1")
_SIZES = {"480": 480, "1280": 1280}


@router.get("/photos/{photo_id}/{size}", response_model=None)
def read_photo(photo_id: str, size: str, request: Request) -> FileResponse | JSONResponse:
    pixels = _SIZES.get(size)
    if pixels is None:
        return JSONResponse({"detail": "unknown photo size"}, status_code=400)
    token = request.cookies.get(get_settings().cookie_name)
    with session_scope() as db:
        photo = db.get(Photo, photo_id)
        if photo is None:
            return JSONResponse({"detail": "photo not found"}, status_code=404)
        listing = db.get(Listing, photo.listing_id)
        if listing is None:
            return JSONResponse({"detail": "photo not found"}, status_code=404)
        actor = _actor(db, token, client_ip(request))
        if actor is None:
            return JSONResponse({"detail": "sign in required"}, status_code=401)
        opened = _open_hunt(db, actor, listing.hunt_id, "viewer", "listings:read")
        if isinstance(opened, str) or not _listing_visible(db, actor, listing):
            return JSONResponse({"detail": "photo not found"}, status_code=404)
        path = photo_file(listing.hunt_id, listing.id, photo.sha256, pixels)
        if not path.is_file():
            return JSONResponse({"detail": "photo not found"}, status_code=404)
        return FileResponse(
            path,
            media_type="image/webp",
            headers={"Cache-Control": "private, max-age=31536000, immutable"},
        )
