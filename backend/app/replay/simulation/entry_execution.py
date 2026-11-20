"""Entry fill modeling from post-decision candles (Phase 5.2.2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.exchanges.types import Candle
from app.replay.simulation.enums import TradeDirection
from app.replay.timeline import candle_close_time, ensure_utc
from app.exchanges.types import Timeframe


@dataclass(frozen=True)
class EntryFillResult:
    filled: bool
    fill_price: float | None = None
    fill_timestamp: datetime | None = None
    candle_open_time: datetime | None = None
    reason: str | None = None
    expired: bool = False
    ambiguous_with_sl: bool = False
    ambiguous_with_tp: bool = False


def try_fill_entry(
    *,
    direction: TradeDirection,
    limit_price: float,
    stop_loss: float,
    take_profits: list[float],
    candle: Candle,
    timeframe: Timeframe,
    decision_timestamp: datetime,
    expires_at: datetime | None,
    clock: datetime,
) -> EntryFillResult:
    """
    Attempt a limit entry on a candle that closed AFTER the decision timestamp.

    Conservative gap rule: if the candle opens through the limit, fill at open.
    """
    decision_timestamp = ensure_utc(decision_timestamp)
    clock = ensure_utc(clock)
    close_t = candle_close_time(candle, timeframe)

    if close_t <= decision_timestamp:
        return EntryFillResult(
            filled=False,
            reason="Candle closed at/before decision timestamp — not eligible for entry.",
        )

    if expires_at is not None and clock > ensure_utc(expires_at):
        return EntryFillResult(
            filled=False,
            expired=True,
            reason="Entry expired before fill.",
        )

    o, h, l = candle.open, candle.high, candle.low
    filled = False
    fill_price: float | None = None

    if direction == "LONG":
        # Limit buy fills only if price trades down to the limit (low <= limit).
        if l > limit_price:
            return EntryFillResult(filled=False, reason="Price never reached LONG limit.")
        if o <= limit_price:
            # Gap / open through limit — conservative fill at open
            filled = True
            fill_price = o
        else:
            # Range crosses limit from above
            filled = True
            fill_price = limit_price
    else:
        # Limit sell fills only if price trades up to the limit (high >= limit).
        if h < limit_price:
            return EntryFillResult(filled=False, reason="Price never reached SHORT limit.")
        if o >= limit_price:
            filled = True
            fill_price = o
        else:
            filled = True
            fill_price = limit_price

    if not filled or fill_price is None:
        return EntryFillResult(filled=False, reason="No entry fill.")

    # Same-candle entry vs SL / TP detection (caller applies ambiguity policy)
    amb_sl = False
    amb_tp = False
    if direction == "LONG":
        amb_sl = l <= stop_loss
        amb_tp = any(h >= tp for tp in take_profits)
    else:
        amb_sl = h >= stop_loss
        amb_tp = any(l <= tp for tp in take_profits)

    return EntryFillResult(
        filled=True,
        fill_price=float(fill_price),
        fill_timestamp=close_t,
        candle_open_time=ensure_utc(candle.timestamp),
        ambiguous_with_sl=amb_sl,
        ambiguous_with_tp=amb_tp,
    )
