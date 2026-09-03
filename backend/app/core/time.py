"""UTC normalization helpers shared by persistence-facing modules."""

from datetime import UTC, datetime


def as_utc(value: datetime) -> datetime:
    """Normalize database timestamps, including SQLite's naive test values, to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def at_or_after(now: datetime, deadline: datetime) -> bool:
    """Compare time boundaries safely with exact `now >= deadline` semantics."""
    return as_utc(now) >= as_utc(deadline)
