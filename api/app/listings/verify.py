import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select

from app.core.clock import utcnow
from app.core.db import session_scope
from app.jobs.models import Job
from app.listings.craigslist import judge, load_posting
from app.listings.models import Listing
from app.listings.presentable import presentable
from app.tenancy.models import Hunt

logger = logging.getLogger(__name__)
RECHECK = timedelta(hours=12)


def store_check(
    row: Listing,
    hunt: Hunt,
    posting: object,
    fetch_error: str | None,
) -> None:
    from app.listings.craigslist import Posting

    page = posting if isinstance(posting, Posting) else None
    ok, error = judge(row.url, row.title, row.notes, page, fetch_error)
    row.link_ok = ok
    row.link_error = None if error is None else error[:200]
    row.link_checked_at = utcnow()
    snap = dict(row.source_snapshot or {})
    craigslist: dict[str, object] = {"ok": ok}
    if error:
        craigslist["error"] = row.link_error
    if page is not None and page.title:
        craigslist["page_title"] = page.title[:140]
    snap["craigslist"] = craigslist
    row.source_snapshot = snap
    row.is_presentable = presentable(hunt, row)


def run_verify_job(job_id: str) -> None:
    with session_scope() as db:
        job = db.get(Job, job_id)
        if job is None or job.kind != "verify" or job.done_at is not None:
            return
        listing = db.get(Listing, str(job.payload.get("listing_id") or ""))
        if listing is None:
            job.done_at = utcnow()
            job.last_error = "listing missing"
            return
        if db.get(Hunt, listing.hunt_id) is None:
            job.done_at = utcnow()
            job.last_error = "hunt missing"
            return
        listing_id = listing.id
        hunt_id = listing.hunt_id
        url = listing.url
    posting, fetch_error = load_posting(url)
    retry_error: str | None = None
    with session_scope() as db:
        listing = db.get(Listing, listing_id)
        hunt = db.get(Hunt, hunt_id)
        if listing is not None and hunt is not None and listing.url == url:
            store_check(listing, hunt, posting, fetch_error)
            if listing.link_error == "the Craigslist link did not open":
                retry_error = listing.link_error
            elif listing.link_ok:
                db.add(
                    Job(
                        kind="verify",
                        payload={"listing_id": listing_id, "hunt_id": hunt_id},
                        run_after=utcnow() + RECHECK,
                    )
                )
    if retry_error:
        _retry(job_id, retry_error)
        return
    _finish(job_id, None)


def _retry(job_id: str, error: str) -> None:
    _finish(job_id, error, retry=True)


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


def claim_verify_job() -> str | None:
    with session_scope() as db:
        job = db.scalar(
            select(Job)
            .where(
                Job.kind == "verify",
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


def queue_unchecked() -> None:
    with session_scope() as db:
        pending = db.scalars(select(Job.payload).where(Job.kind == "verify", Job.done_at.is_(None)))
        waiting = {
            str(item.get("listing_id"))
            for item in pending
            if isinstance(item, dict) and item.get("listing_id")
        }
        rows = db.execute(
            select(Listing.id, Listing.hunt_id)
            .join(Hunt, Hunt.id == Listing.hunt_id)
            .where(Hunt.schema_id == "nyc-rental-v1", Listing.link_checked_at.is_(None))
        ).all()
        for listing_id, hunt_id in rows:
            if listing_id in waiting:
                continue
            db.add(
                Job(
                    kind="verify",
                    payload={"listing_id": listing_id, "hunt_id": hunt_id},
                    run_after=utcnow(),
                )
            )


async def verify_loop(stop: asyncio.Event) -> None:
    await asyncio.to_thread(queue_unchecked)
    while not stop.is_set():
        job_id = await asyncio.to_thread(claim_verify_job)
        if job_id is not None:
            try:
                await asyncio.to_thread(run_verify_job, job_id)
            except Exception:
                logger.exception("verify job %s failed", job_id)
                await asyncio.to_thread(
                    _finish, job_id, "the Craigslist link did not open", retry=True
                )
            continue
        try:
            await asyncio.wait_for(stop.wait(), timeout=2)
        except TimeoutError:
            continue
