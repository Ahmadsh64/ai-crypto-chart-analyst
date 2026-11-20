"""Historical candle integrity classification (Phase 5.2.5).

Does not fabricate missing candles. Distinguishes continuous, gapped,
invalid, incomplete, and unavailable series.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.replay.timeline import (
    ensure_utc,
    is_aligned_open,
    is_valid_candle,
    sanitize_series,
)


class IntegrityStatus(str, Enum):
    CONTINUOUS = "continuous"
    GAPS = "gaps"
    INVALID = "invalid"
    INCOMPLETE = "incomplete"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class SeriesIntegrityReport:
    timeframe: Timeframe
    status: IntegrityStatus
    input_count: int
    cleaned_count: int
    duplicate_opens_dropped: int
    invalid_dropped: int
    misaligned_dropped: int
    gap_count: int
    limitations: list[str] = field(default_factory=list)
    first_open: datetime | None = None
    last_open: datetime | None = None


def classify_series_integrity(
    candles: list[Candle],
    *,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    timeframe: Timeframe,
) -> SeriesIntegrityReport:
    """Sanitize and classify a TF series without fabricating OHLC."""
    input_count = len(candles)
    if input_count == 0:
        return SeriesIntegrityReport(
            timeframe=timeframe,
            status=IntegrityStatus.UNAVAILABLE,
            input_count=0,
            cleaned_count=0,
            duplicate_opens_dropped=0,
            invalid_dropped=0,
            misaligned_dropped=0,
            gap_count=0,
            limitations=[f"{timeframe.value}: unavailable (empty input)."],
        )

    # Pre-count issues for reporting (sanitize also drops them).
    invalid_dropped = 0
    misaligned_dropped = 0
    open_keys: list[datetime] = []
    for c in candles:
        if c.exchange != exchange or c.market_type != market_type:
            continue
        if c.symbol.upper() != symbol.upper():
            continue
        if not is_valid_candle(c):
            invalid_dropped += 1
            continue
        key = ensure_utc(c.timestamp)
        if not is_aligned_open(key, timeframe):
            misaligned_dropped += 1
            continue
        open_keys.append(key)

    duplicate_opens_dropped = max(0, len(open_keys) - len(set(open_keys)))

    cleaned, gaps, limitations = sanitize_series(
        candles,
        exchange=exchange,
        symbol=symbol,
        market_type=market_type,
        timeframe=timeframe,
    )

    if not cleaned:
        status = IntegrityStatus.INVALID if invalid_dropped or misaligned_dropped else IntegrityStatus.INCOMPLETE
        return SeriesIntegrityReport(
            timeframe=timeframe,
            status=status,
            input_count=input_count,
            cleaned_count=0,
            duplicate_opens_dropped=duplicate_opens_dropped,
            invalid_dropped=invalid_dropped,
            misaligned_dropped=misaligned_dropped,
            gap_count=len(gaps),
            limitations=limitations
            or [f"{timeframe.value}: incomplete (no valid candles)."],
        )

    if gaps:
        status = IntegrityStatus.GAPS
    elif invalid_dropped or misaligned_dropped:
        # Valid continuous cleaned series, but input had defects that were dropped.
        status = IntegrityStatus.INVALID
    else:
        status = IntegrityStatus.CONTINUOUS

    return SeriesIntegrityReport(
        timeframe=timeframe,
        status=status,
        input_count=input_count,
        cleaned_count=len(cleaned),
        duplicate_opens_dropped=duplicate_opens_dropped,
        invalid_dropped=invalid_dropped,
        misaligned_dropped=misaligned_dropped,
        gap_count=len(gaps),
        limitations=limitations,
        first_open=ensure_utc(cleaned[0].timestamp),
        last_open=ensure_utc(cleaned[-1].timestamp),
    )


def validate_pagination_order(
    pages: list[list[Candle]],
    *,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    timeframe: Timeframe,
) -> tuple[list[Candle], list[str]]:
    """
    Merge paginated candle pages and ensure sanitize removes cross-page
    duplicates without inventing bars or reversing chronology.
    """
    notes: list[str] = []
    merged: list[Candle] = []
    for i, page in enumerate(pages):
        if not page:
            notes.append(f"page[{i}]: empty")
            continue
        opens = [ensure_utc(c.timestamp) for c in page]
        if opens != sorted(opens):
            notes.append(f"page[{i}]: not sorted chronologically (will be sorted).")
        merged.extend(page)

    cleaned, gaps, lim = sanitize_series(
        merged,
        exchange=exchange,
        symbol=symbol,
        market_type=market_type,
        timeframe=timeframe,
    )
    notes.extend(lim)
    if gaps:
        notes.append(f"merged series has {len(gaps)} gap(s).")
    # Chronology guarantee
    for i in range(1, len(cleaned)):
        if ensure_utc(cleaned[i].timestamp) < ensure_utc(cleaned[i - 1].timestamp):
            raise AssertionError("sanitize_series produced non-chronological order")
    return cleaned, notes
