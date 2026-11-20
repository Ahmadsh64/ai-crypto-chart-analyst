"""No-look-ahead validation for historical prefixes (Phase 5.2.1)."""

from __future__ import annotations

from datetime import datetime

from app.exchanges.types import Candle, Timeframe
from app.replay.timeline import candle_close_time, ensure_utc


class LookAheadError(ValueError):
    """Raised when a candle that closes after the replay clock is present."""


def assert_no_future_candles(
    candles: list[Candle],
    *,
    timeframe: Timeframe,
    clock: datetime,
) -> None:
    """Reject any candle whose close_time is after the replay clock."""
    clock = ensure_utc(clock)
    for c in candles:
        ct = candle_close_time(c, timeframe)
        if ct > clock:
            raise LookAheadError(
                f"Future candle rejected for {timeframe.value}: "
                f"open={ensure_utc(c.timestamp).isoformat()} "
                f"close={ct.isoformat()} clock={clock.isoformat()}"
            )


def filter_closed_prefix(
    candles: list[Candle],
    *,
    timeframe: Timeframe,
    clock: datetime,
) -> list[Candle]:
    """
    Return only candles confirmed at ``clock``.

    Does not fabricate gaps. Validates that the result contains no future bars.
    """
    clock = ensure_utc(clock)
    prefix = [c for c in candles if candle_close_time(c, timeframe) <= clock]
    assert_no_future_candles(prefix, timeframe=timeframe, clock=clock)
    return prefix
