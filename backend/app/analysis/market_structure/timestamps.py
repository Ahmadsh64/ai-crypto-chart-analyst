"""UTC timestamp validation for the Market Structure engine boundary."""

from __future__ import annotations

from datetime import datetime, timezone


class NaiveTimestampError(ValueError):
    """Raised when a naive datetime reaches the market-structure engine."""


def ensure_utc(ts: datetime, *, field: str = "timestamp") -> datetime:
    """
    Require timezone-aware timestamps and normalize to UTC.

    Naive datetimes are rejected — never labeled with a misleading Z suffix.
    """
    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
        raise NaiveTimestampError(
            f"Market Structure requires timezone-aware UTC timestamps; "
            f"got naive datetime for {field}: {ts!r}"
        )
    return ts.astimezone(timezone.utc)


def format_utc_key(ts: datetime) -> str:
    """Format an aware timestamp as genuine UTC for deterministic event keys."""
    utc = ensure_utc(ts, field="event_key")
    return utc.strftime("%Y%m%dT%H%M%SZ")
