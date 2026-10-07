import io

from PIL import Image
from sqlalchemy import select
from tests.test_auth import PASSWORD, Client
from tests.test_listings import _body

from app.core.db import session_scope
from app.jobs.models import Job
from app.photos.fetch import image_urls_from_html, is_public_url
from app.photos.jobs import run_photo_job
from app.photos.models import Photo


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), (180, 40, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


def _admin() -> Client:
    client = Client()
    created = client.post(
        "/api/v1/setup",
        {
            "token": "bootstrap-token-value",
            "email": "admin@example.com",
            "password": PASSWORD,
            "display_name": "Orpheus",
        },
    )
    if created.status_code != 200:
        signed = client.post(
            "/api/v1/auth/password/login",
            {"email": "admin@example.com", "password": PASSWORD},
        )
        assert signed.status_code == 200, signed.text
    return client


def test_private_photo_urls_are_blocked() -> None:
    assert is_public_url("http://127.0.0.1/secret") is False
    assert is_public_url("http://169.254.169.254/latest") is False
    assert is_public_url("http://10.1.1.1/photo.jpg") is False
    assert is_public_url("http://192.168.1.8/photo.jpg") is False
    assert is_public_url("file:///etc/passwd") is False
    assert is_public_url("http://localhost/photo.jpg") is False


def test_preview_images_are_taken_from_the_page() -> None:
    html = '<meta property="og:image" content="https://cdn.example/a.jpg">'
    assert image_urls_from_html(html, "https://cdn.example/listing") == [
        "https://cdn.example/a.jpg"
    ]


def test_photo_job_keeps_one_copy(monkeypatch) -> None:
    png = _png()
    monkeypatch.setattr("app.photos.jobs.is_public_url", lambda _url: True)
    monkeypatch.setattr(
        "app.photos.jobs.fetch_bytes",
        lambda _url, _timeout: (png, "image/png"),
    )
    admin = _admin()
    hunt = admin.post(
        "/api/v1/hunts",
        {
            "name": "NYC photos",
            "slug": "nyc-photos",
            "kind": "rental",
            "schema": "nyc-rental-v1",
            "criteria": {"price_ceiling": 3000},
            "rating_scale": 5,
        },
    )
    assert hunt.status_code == 201, hunt.text
    hunt_id = hunt.json()["id"]
    created = admin.post(
        "/api/v1/listings",
        _body(
            hunt_id,
            external_id="photo-1",
            url="https://cdn.example/listing",
            photos=[{"url": "https://cdn.example/a.jpg", "caption": "kitchen"}],
        ),
    )
    assert created.status_code == 201, created.text
    listing_id = created.json()["listing"]["id"]
    with session_scope() as db:
        jobs = db.scalars(select(Job).where(Job.kind == "photo")).all()
        match = next(job for job in jobs if job.payload.get("listing_id") == listing_id)
        job_id = match.id
    run_photo_job(job_id)
    with session_scope() as db:
        again = db.get(Job, job_id)
        assert again is not None
        again.done_at = None
    run_photo_job(job_id)
    listed = admin.get(f"/api/v1/listings?hunt_id={hunt_id}&presentable=false")
    photos = listed.json()["listings"][0]["photos"]
    assert len(photos) == 1
    assert photos[0]["is_cover"] is True
    fetched = admin.get(photos[0]["thumb"])
    assert fetched.status_code == 200, fetched.text
    assert fetched.headers["content-type"].startswith("image/webp")
    with session_scope() as db:
        assert db.scalar(select(Photo).where(Photo.listing_id == listing_id)) is not None
