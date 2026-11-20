"""Stop-loss and take-profit execution (Phase 5.2.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.exchanges.types import Candle, Timeframe
from app.replay.simulation.enums import AmbiguityPolicy, TradeDirection
from app.replay.timeline import candle_close_time, ensure_utc


@dataclass
class ExitHit:
    kind: str  # "sl" | "tp"
    price: float
    tp_index: int | None = None
    quantity: float = 0.0


@dataclass
class ExitProcessResult:
    hits: list[ExitHit] = field(default_factory=list)
    ambiguous: bool = False
    ambiguity_warning: str | None = None
    policy_applied: str | None = None
    candle_close_time: datetime | None = None


def _sl_touched(direction: TradeDirection, candle: Candle, stop: float) -> bool:
    if direction == "LONG":
        return candle.low <= stop
    return candle.high >= stop


def _tp_touched(direction: TradeDirection, candle: Candle, tp: float) -> bool:
    if direction == "LONG":
        return candle.high >= tp
    return candle.low <= tp


def _sl_fill_price(direction: TradeDirection, candle: Candle, stop: float) -> float:
    """Conservative gap: do not fill better than the open through the stop."""
    if direction == "LONG":
        if candle.open <= stop:
            return candle.open
        return stop
    if candle.open >= stop:
        return candle.open
    return stop


def _tp_fill_price(direction: TradeDirection, candle: Candle, tp: float) -> float:
    if direction == "LONG":
        if candle.open >= tp:
            return candle.open
        return tp
    if candle.open <= tp:
        return candle.open
    return tp


def resolve_same_candle_order(
    *,
    direction: TradeDirection,
    candle: Candle,
    stop: float,
    pending_tps: list[tuple[int, float]],
    policy: AmbiguityPolicy,
    lower_tf_candles: list[Candle] | None,
    lower_tf: Timeframe | None,
) -> ExitProcessResult:
    """
    Determine SL/TP event order within one OHLC candle.

    Default conservative_stop_first: if SL and any TP touch, SL wins first.
    """
    close_t = candle_close_time(candle, Timeframe.M5)
    sl_hit = _sl_touched(direction, candle, stop)
    tp_hits = [(i, p) for i, p in pending_tps if _tp_touched(direction, candle, p)]

    if not sl_hit and not tp_hits:
        return ExitProcessResult(candle_close_time=close_t)

    if policy == "use_lower_timeframe_if_available" and lower_tf_candles and lower_tf:
        ordered = _order_from_lower_tf(
            direction=direction,
            parent=candle,
            stop=stop,
            pending_tps=pending_tps,
            lower=lower_tf_candles,
            lower_tf=lower_tf,
        )
        if ordered is not None:
            ordered.policy_applied = policy
            return ordered
        # Fall through to mark ambiguous if unresolved
        policy = "mark_ambiguous"

    if sl_hit and tp_hits:
        if policy == "mark_ambiguous":
            return ExitProcessResult(
                hits=[
                    ExitHit(
                        kind="sl",
                        price=_sl_fill_price(direction, candle, stop),
                    )
                ],
                ambiguous=True,
                ambiguity_warning=(
                    "SL and TP touched in the same candle; order unknown — "
                    "marked ambiguous (conservative SL recorded)."
                ),
                policy_applied=policy,
                candle_close_time=close_t,
            )
        # conservative_stop_first
        return ExitProcessResult(
            hits=[
                ExitHit(
                    kind="sl",
                    price=_sl_fill_price(direction, candle, stop),
                )
            ],
            ambiguous=False,
            ambiguity_warning=(
                "SL and TP touched in the same candle; applied conservative_stop_first."
            ),
            policy_applied="conservative_stop_first",
            candle_close_time=close_t,
        )

    if sl_hit:
        return ExitProcessResult(
            hits=[
                ExitHit(
                    kind="sl",
                    price=_sl_fill_price(direction, candle, stop),
                )
            ],
            policy_applied=policy,
            candle_close_time=close_t,
        )

    # Only TPs — process in index order (TP1 then TP2…) if all touch same bar:
    # without path evidence, mark ambiguous for multiple TPs unless only one.
    if len(tp_hits) > 1:
        if policy == "mark_ambiguous":
            # Still close TP1 only conservatively? Spec: mark ambiguous
            first_i, first_p = sorted(tp_hits, key=lambda x: x[0])[0]
            return ExitProcessResult(
                hits=[
                    ExitHit(
                        kind="tp",
                        price=_tp_fill_price(direction, candle, first_p),
                        tp_index=first_i,
                    )
                ],
                ambiguous=True,
                ambiguity_warning=(
                    "Multiple TP levels touched in the same candle; order unknown."
                ),
                policy_applied=policy,
                candle_close_time=close_t,
            )
        # conservative: execute lowest index TP only this candle (stop_first spirit)
        first_i, first_p = sorted(tp_hits, key=lambda x: x[0])[0]
        return ExitProcessResult(
            hits=[
                ExitHit(
                    kind="tp",
                    price=_tp_fill_price(direction, candle, first_p),
                    tp_index=first_i,
                )
            ],
            ambiguity_warning=(
                "Multiple TP levels touched; applied single lowest-index TP this candle."
            ),
            policy_applied="conservative_stop_first",
            candle_close_time=close_t,
        )

    i, p = tp_hits[0]
    return ExitProcessResult(
        hits=[
            ExitHit(
                kind="tp",
                price=_tp_fill_price(direction, candle, p),
                tp_index=i,
            )
        ],
        policy_applied=policy,
        candle_close_time=close_t,
    )


def _order_from_lower_tf(
    *,
    direction: TradeDirection,
    parent: Candle,
    stop: float,
    pending_tps: list[tuple[int, float]],
    lower: list[Candle],
    lower_tf: Timeframe,
) -> ExitProcessResult | None:
    """Walk lower-TF bars inside the parent bar chronologically."""
    parent_open = ensure_utc(parent.timestamp)
    parent_close = candle_close_time(parent, Timeframe.M5)
    # If parent is already 5m, lower TF cannot refine path.
    bars = [
        c
        for c in lower
        if ensure_utc(c.timestamp) >= parent_open
        and candle_close_time(c, lower_tf) <= parent_close
    ]
    bars.sort(key=lambda c: ensure_utc(c.timestamp))
    if not bars:
        return None

    hits: list[ExitHit] = []
    remaining_tps = list(pending_tps)
    for bar in bars:
        if _sl_touched(direction, bar, stop):
            hits.append(
                ExitHit(
                    kind="sl",
                    price=_sl_fill_price(direction, bar, stop),
                )
            )
            return ExitProcessResult(
                hits=hits,
                ambiguous=False,
                policy_applied="use_lower_timeframe_if_available",
                candle_close_time=candle_close_time(bar, lower_tf),
            )
        newly = []
        for i, p in remaining_tps:
            if _tp_touched(direction, bar, p):
                hits.append(
                    ExitHit(
                        kind="tp",
                        price=_tp_fill_price(direction, bar, p),
                        tp_index=i,
                    )
                )
                newly.append((i, p))
        remaining_tps = [t for t in remaining_tps if t not in newly]
        if hits and not remaining_tps:
            break

    if not hits:
        return None
    # If both SL and TP somehow still unresolved in path — shouldn't happen
    return ExitProcessResult(
        hits=hits,
        ambiguous=False,
        policy_applied="use_lower_timeframe_if_available",
        candle_close_time=candle_close_time(bars[-1], lower_tf),
    )
