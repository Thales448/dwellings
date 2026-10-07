import asyncio
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.db import session_scope
from app.jobs.models import Job
from app.listings.models import Listing
from app.photos.fetch import (
    PhotoFetchError,
    fetch_bytes,
    image_urls_from_html,
    is_public_url,
    looks_like_image,
)
from app.photos.models import Photo
from app.photos.store import keep_image

logger = logging.getLogger(__name__)


def _specs(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    specs: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            specs.append({"url": item})
        elif isinstance(item, dict) and isinstance(item.get("url"), str):
            specs.append(item)
    return specs


def _page_images(listing: Listing) -> list[dict[str, Any]]:
    if not is_public_url(listing.url):
        return []
    try:
        data, content_type = fetch_bytes(listing.url, get_settings().photo_fetch_timeout)
    except PhotoFetchError as exc:
        logger.info("photo page skipped for %s: %s", listing.id, exc)
        return []
    if "html" not in content_type:
        return []
    html = data[:1_000_000].decode("utf-8", errors="ignore")
    return [{"url": url} for url in image_urls_from_html(html, listing.url)]


def run_photo_job(job_id: str) -> None:
    with session_scope() as db:
        job = db.get(Job, job_id)
        if job is None or job.kind != "photo" or job.done_at is not None:
            return
        payload = dict(job.payload)
        listing = db.get(Listing, str(payload.get("listing_id") or ""))
        if listing is None:
            job.done_at = utcnow()
            job.last_error = "listing missing"
            return
        specs = _specs(payload.get("photos"))
        if not specs:
            already = db.scalar(select(Photo.id).where(Photo.listing_id == listing.id))
            if already is not None:
                job.done_at = utcnow()
                return
        listing_id = listing.id
    if not specs:
        with session_scope() as db:
            listing = db.get(Listing, listing_id)
            specs = _page_images(listing) if listing is not None else []
        if not specs:
            _finish(job_id, None)
            return
    saved = 0
    errors: list[str] = []
    timeout = get_settings().photo_fetch_timeout
    for spec in specs:
        source = str(spec.get("url") or "")
        if not is_public_url(source):
            errors.append("blocked url")
            continue
        try:
            data, content_type = fetch_bytes(source, timeout)
        except PhotoFetchError as exc:
            errors.append(str(exc))
            continue
        if not looks_like_image(data, content_type):
            errors.append("not an image")
            continue
        kitchen = spec.get("shows_kitchen")
        caption = spec.get("caption")
        with session_scope() as db:
            listing = db.get(Listing, listing_id)
            if listing is None:
                break
            if keep_image(
                db,
                listing,
                data,
                original_url=source,
                caption=caption if isinstance(caption, str) else None,
                shows_kitchen=kitchen if isinstance(kitchen, bool) else None,
                origin="url",
            ):
                saved += 1
    if saved == 0 and errors:
        _finish(job_id, errors[0], retry=True)
        return
    _finish(job_id, None)


def _finish(job_id: str, error: str | None, *, retry: bool = False) -> None:
    with session_scope() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        if error and retry and job.attempts < 5:
            job.last_error = error[:500]
            job.run_after = utcnow() + timedelta(minutes=2**job.attempts)
            return
        job.done_at = utcnow()
        job.last_error = error[:500] if error else None


def claim_photo_job() -> str | None:
    with session_scope() as db:
        job = db.scalar(
            select(Job)
            .where(
                Job.kind == "photo",
                Job.done_at.is_(None),
                Job.run_after <= utcnow(),
                Job.attempts < 5,
            )
            .order_by(Job.run_after.asc())
            .limit(1)
        )
        if job is None:
            return None
        job.attempts += 1
        return job.id


async def photo_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        job_id = await asyncio.to_thread(claim_photo_job)
        if job_id is not None:
            try:
                await asyncio.to_thread(run_photo_job, job_id)
            except Exception:
                logger.exception("photo job %s failed", job_id)
                await asyncio.to_thread(_finish, job_id, "photo job failed", retry=True)
            continue
        try:
            await asyncio.wait_for(stop.wait(), timeout=2)
        except TimeoutError:
            continue
