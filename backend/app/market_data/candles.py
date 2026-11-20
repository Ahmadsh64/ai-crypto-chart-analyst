"""Candle query helpers, timeframe utilities, and pagination."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.exchanges.types import Candle, Timeframe

TIMEFRAME_SECONDS: dict[Timeframe, int] = {
    Timeframe.M1: 60,
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.M30: 1800,
    Timeframe.H1: 3600,
    Timeframe.H4: 14400,
    Timeframe.D1: 86400,
}

MAX_PAGE_SIZE = 1000


def timeframe_to_seconds(timeframe: Timeframe) -> int:
    return TIMEFRAME_SECONDS[timeframe]


def clamp_page_size(limit: int, *, max_size: int = MAX_PAGE_SIZE) -> int:
    return max(1, min(limit, max_size))


def page_boundaries(
    *,
    limit: int,
    end: datetime | None = None,
    max_size: int = MAX_PAGE_SIZE,
) -> list[tuple[int, datetime | None]]:
    """
    Build (page_limit, end_time) pages for historical pagination walking backward.

    Returns newest-first page specs; callers should reverse-merge results.
    """
    remaining = max(1, limit)
    cursor_end = end
    pages: list[tuple[int, datetime | None]] = []
    while remaining > 0:
        page_limit = clamp_page_size(remaining, max_size=max_size)
        pages.append((page_limit, cursor_end))
        remaining -= page_limit
        # Placeholder cursor; adapters advance using the oldest candle of each page.
        if remaining > 0 and cursor_end is None:
            # First page without end uses exchange default (most recent).
            # Subsequent pages require adapter to set end from fetched data.
            cursor_end = datetime.now(timezone.utc)
    return pages


def previous_page_end(oldest: Candle) -> datetime:
    """Exclusive end cursor just before the oldest candle of the prior page."""
    return oldest.timestamp - timedelta(milliseconds=1)
