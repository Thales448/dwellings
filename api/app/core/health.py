import shutil
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.core.db import get_engine


def _job_lag_seconds() -> float:
    try:
        with get_engine().connect() as connection:
            oldest = connection.execute(
                text("SELECT MIN(run_after) FROM jobs WHERE done_at IS NULL")
            ).scalar()
    except SQLAlchemyError:
        return 0.0
    if oldest is None:
        return 0.0
    if isinstance(oldest, str):
        parsed = datetime.fromisoformat(oldest)
    elif isinstance(oldest, datetime):
        parsed = oldest
    else:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    lag = (datetime.now(UTC) - parsed).total_seconds()
    return max(0.0, lag)


def health_payload(settings: Settings) -> tuple[dict[str, Any], int]:
    db = "ok"
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        db = "error"

    disk: dict[str, Any] = {"path": str(settings.data_dir)}
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(settings.data_dir)
        disk["free_bytes"] = usage.free
        disk["status"] = "ok"
    except OSError as exc:
        disk["status"] = "error"
        disk["error"] = str(exc)

    job_lag = _job_lag_seconds()
    ok = db == "ok" and disk.get("status") == "ok"
    body = {
        "status": "ok" if ok else "degraded",
        "db": db,
        "disk": disk,
        "job_lag_seconds": job_lag,
    }
    return body, 200 if ok else 503
