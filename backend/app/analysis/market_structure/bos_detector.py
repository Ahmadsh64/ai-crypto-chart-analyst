"""Break of Structure (BOS) helpers — close beyond level, no wick-only."""

from __future__ import annotations

from datetime import datetime

from app.analysis.market_structure.models import StructureDirection, SwingKind, SwingPoint
from app.analysis.market_structure.timestamps import format_utc_key
from app.exchanges.types import Candle


def break_event_key(
    kind: str,
    direction: StructureDirection,
    symbol: str,
    timeframe: str,
    level_ts: datetime,
    break_ts: datetime,
) -> str:
    return (
        f"{kind}:{direction.value}:{symbol.upper()}:{timeframe}:"
        f"{format_utc_key(level_ts)}:{format_utc_key(break_ts)}"
    )


def is_bullish_close_break(candle: Candle, level: float) -> bool:
    """BOS/CHoCH require close above level — wick alone is insufficient."""
    return candle.close > level


def is_bearish_close_break(candle: Candle, level: float) -> bool:
    return candle.close < level


def candle_body(candle: Candle) -> float:
    return abs(float(candle.close) - float(candle.open))


def latest_unbroken_swing(
    swings: list[SwingPoint],
    kind: SwingKind,
    broken_keys: set[str],
) -> SwingPoint | None:
    """Most recent confirmed swing of `kind` whose level has not been broken yet."""
    for swing in reversed(swings):
        if swing.kind != kind or not swing.confirmed:
            continue
        if swing.event_key in broken_keys:
            continue
        return swing
    return None
