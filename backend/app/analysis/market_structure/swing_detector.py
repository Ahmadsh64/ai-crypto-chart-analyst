"""Confirmed Swing High / Swing Low detection (no look-ahead)."""

from __future__ import annotations

from datetime import datetime

from app.analysis.market_structure.config import MarketStructureConfig
from app.analysis.market_structure.models import SwingKind, SwingPoint
from app.analysis.market_structure.timestamps import format_utc_key
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe


def _event_key(
    kind: SwingKind,
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    timeframe: Timeframe,
    candle_ts: datetime,
) -> str:
    ts = format_utc_key(candle_ts)
    return (
        f"swing:{kind.value}:{exchange.value}:{market_type.value}:"
        f"{symbol.upper()}:{timeframe.value}:{ts}"
    )


def detect_confirmed_swings(
    candles: list[Candle],
    *,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    timeframe: Timeframe,
    config: MarketStructureConfig,
) -> list[SwingPoint]:
    """
    Detect confirmed pivots.

    Tie-breaking (equal_extreme_tie_rule=strict_inequality):
    A candidate must be *strictly* higher/lower than every left and right neighbour.
    Equal highs/lows on either side disqualify the pivot (no duplicate equal pivots).

    Confirmation: pivot at index i is confirmed only when candles
    [i+1 .. i+swing_right] all exist and are closed (or treated as closed in the
    historical closed-only series). The confirmation timestamp is the open time
    of candle i+swing_right (the last right-side bar that sealed the pivot).
    """
    left = config.swing_left
    right = config.swing_right
    n = len(candles)
    if n < left + right + 1:
        return []

    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    swings: list[SwingPoint] = []

    # Last index that can be confirmed: need `right` closed bars after it.
    last_confirmable = n - 1 - right
    for i in range(left, last_confirmable + 1):
        # Right-side bars must be present (guaranteed by range) — for live feeds
        # only closed candles are passed when use_closed_candles_only=True.
        right_slice = candles[i + 1 : i + 1 + right]
        if config.use_closed_candles_only and any(not c.is_closed for c in right_slice):
            continue

        # Swing High: strict greater than left and right windows.
        is_sh = all(highs[i] > highs[j] for j in range(i - left, i)) and all(
            highs[i] > highs[j] for j in range(i + 1, i + 1 + right)
        )
        # Swing Low: strict less than left and right windows.
        is_sl = all(lows[i] < lows[j] for j in range(i - left, i)) and all(
            lows[i] < lows[j] for j in range(i + 1, i + 1 + right)
        )

        confirm_ts = candles[i + right].timestamp
        if is_sh:
            swings.append(
                SwingPoint(
                    event_key=_event_key(
                        SwingKind.HIGH, exchange, market_type, symbol, timeframe, candles[i].timestamp
                    ),
                    exchange=exchange,
                    symbol=symbol.upper(),
                    market_type=market_type,
                    timeframe=timeframe,
                    kind=SwingKind.HIGH,
                    price=float(highs[i]),
                    candle_timestamp=candles[i].timestamp,
                    confirmation_timestamp=confirm_ts,
                    confirmed=True,
                    config_version=config.config_version,
                    candle_index=i,
                )
            )
        if is_sl:
            swings.append(
                SwingPoint(
                    event_key=_event_key(
                        SwingKind.LOW, exchange, market_type, symbol, timeframe, candles[i].timestamp
                    ),
                    exchange=exchange,
                    symbol=symbol.upper(),
                    market_type=market_type,
                    timeframe=timeframe,
                    kind=SwingKind.LOW,
                    price=float(lows[i]),
                    candle_timestamp=candles[i].timestamp,
                    confirmation_timestamp=confirm_ts,
                    confirmed=True,
                    config_version=config.config_version,
                    candle_index=i,
                )
            )

    # Stable order: by candle index then high before low at same bar.
    swings.sort(key=lambda s: (s.candle_index, 0 if s.kind == SwingKind.HIGH else 1))
    return swings


def detect_unconfirmed_candidates(
    candles: list[Candle],
    *,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    timeframe: Timeframe,
    config: MarketStructureConfig,
) -> list[SwingPoint]:
    """
    Candidate pivots that look like swings vs left window but lack full right confirmation.

    Never treated as confirmed signals.
    """
    left = config.swing_left
    right = config.swing_right
    n = len(candles)
    if n < left + 1:
        return []

    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    out: list[SwingPoint] = []
    # Candidates near the end that don't yet have `right` closed bars after them.
    start = max(left, n - right - left)
    for i in range(start, n):
        right_available = n - 1 - i
        if right_available >= right:
            continue  # would be confirmable via confirmed detector
        if i < left:
            continue
        left_ok_h = all(highs[i] > highs[j] for j in range(i - left, i))
        left_ok_l = all(lows[i] < lows[j] for j in range(i - left, i))
        right_h_ok = all(highs[i] > highs[j] for j in range(i + 1, n)) if i + 1 < n else True
        right_l_ok = all(lows[i] < lows[j] for j in range(i + 1, n)) if i + 1 < n else True
        if left_ok_h and right_h_ok:
            out.append(
                SwingPoint(
                    event_key=_event_key(
                        SwingKind.HIGH, exchange, market_type, symbol, timeframe, candles[i].timestamp
                    )
                    + ":unconfirmed",
                    exchange=exchange,
                    symbol=symbol.upper(),
                    market_type=market_type,
                    timeframe=timeframe,
                    kind=SwingKind.HIGH,
                    price=float(highs[i]),
                    candle_timestamp=candles[i].timestamp,
                    confirmation_timestamp=candles[i].timestamp,
                    confirmed=False,
                    config_version=config.config_version,
                    candle_index=i,
                )
            )
        if left_ok_l and right_l_ok:
            out.append(
                SwingPoint(
                    event_key=_event_key(
                        SwingKind.LOW, exchange, market_type, symbol, timeframe, candles[i].timestamp
                    )
                    + ":unconfirmed",
                    exchange=exchange,
                    symbol=symbol.upper(),
                    market_type=market_type,
                    timeframe=timeframe,
                    kind=SwingKind.LOW,
                    price=float(lows[i]),
                    candle_timestamp=candles[i].timestamp,
                    confirmation_timestamp=candles[i].timestamp,
                    confirmed=False,
                    config_version=config.config_version,
                    candle_index=i,
                )
            )
    return out
