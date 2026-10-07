from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def iso_utc(value: datetime | None) -> str | None:
    """Serialize datetimes as UTC with an explicit offset so browsers do not treat them as local."""
    if value is None:
        return None
    return as_utc(value).isoformat()
