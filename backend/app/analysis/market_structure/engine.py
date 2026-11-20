"""
Market Structure Engine — deterministic swing / BOS / CHoCH / MSS analysis.

Operates on normalized OHLCV only. No look-ahead: pivots confirm only after
`swing_right` subsequent closed candles; breaks use candle CLOSE.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from app.analysis.indicators.volatility import atr as calc_atr
from app.analysis.market_structure.bos_detector import (
    break_event_key,
    candle_body,
    is_bearish_close_break,
    is_bullish_close_break,
    latest_unbroken_swing,
)
from app.analysis.market_structure.choch_detector import bias_after_break, classify_break
from app.analysis.market_structure.classifier import classify_swings, derive_bias_from_swings
from app.analysis.market_structure.config import DEFAULT_STRUCTURE_CONFIG, MarketStructureConfig
from app.analysis.market_structure.models import (
    AmbiguousDualBreak,
    BreakKind,
    CHoCHEvent,
    MarketStructureResult,
    MarketStructureSnapshot,
    MSSEvent,
    StructureBias,
    StructureBreak,
    StructureDirection,
    SwingKind,
    SwingPoint,
)
from app.analysis.market_structure.mss_detector import build_mss_from_choch, has_displacement
from app.analysis.market_structure.swing_detector import (
    detect_confirmed_swings,
    detect_unconfirmed_candidates,
)
from app.analysis.market_structure.timestamps import ensure_utc, format_utc_key
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe


def _prepare_candles(
    candles: list[Candle],
    config: MarketStructureConfig,
) -> list[Candle]:
    ordered = sorted(candles, key=lambda c: c.timestamp)
    if config.use_closed_candles_only:
        ordered = [c for c in ordered if c.is_closed]
    # Deduplicate by timestamp keeping last; enforce aware UTC.
    by_ts: dict[datetime, Candle] = {}
    for c in ordered:
        ts = ensure_utc(c.timestamp, field="candle.timestamp")
        by_ts[ts] = c.model_copy(update={"timestamp": ts})
    return [by_ts[k] for k in sorted(by_ts.keys())]


def _atr_series(candles: list[Candle], period: int) -> np.ndarray:
    if not candles:
        return np.array([], dtype=float)
    highs = np.asarray([c.high for c in candles], dtype=float)
    lows = np.asarray([c.low for c in candles], dtype=float)
    closes = np.asarray([c.close for c in candles], dtype=float)
    return calc_atr(highs, lows, closes, period)


def _assign_bos_segments(
    bos_events: list[StructureBreak],
    opposing_or_later_breaks: list[tuple[datetime, StructureDirection]],
    series_end: datetime | None,
) -> list[StructureBreak]:
    """
    Derive time-scoped BOS segments from subsequent structure events.

    End rules (no invented invalidation events):
    - Later BOS (any direction) → segment ends at that candle (superseded).
    - Opposite-direction CHoCH/BOS after this break → segment ends there (invalidated).
    - Otherwise → end at last series candle; segment_active=True.
    """
    out: list[StructureBreak] = []
    for idx, bos in enumerate(bos_events):
        start = bos.candle_timestamp
        end_candidates: list[datetime] = []
        if idx + 1 < len(bos_events):
            end_candidates.append(bos_events[idx + 1].candle_timestamp)
        for ts, direction in opposing_or_later_breaks:
            if ts > start and direction != bos.direction:
                end_candidates.append(ts)
        if end_candidates:
            end = min(end_candidates)
            active = False
        else:
            end = series_end
            active = series_end is not None
        out.append(
            bos.model_copy(
                update={
                    "segment_start": start,
                    "segment_end": end,
                    "segment_active": active,
                }
            )
        )
    return out


def analyze_market_structure(
    candles: list[Candle],
    *,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    timeframe: Timeframe,
    config: MarketStructureConfig | None = None,
    include_unconfirmed: bool = False,
) -> MarketStructureResult:
    """
    Full historical Market Structure analysis.

    Incremental live updates should call this with the growing closed-candle
    series; event_keys are deterministic so duplicates can be filtered upstream.
    """
    cfg = config or DEFAULT_STRUCTURE_CONFIG
    if cfg.detection_mode.value != "balanced":
        raise ValueError(f"Detection mode {cfg.detection_mode} is not implemented in Phase 3.2")

    series = _prepare_candles(candles, cfg)
    symbol_u = symbol.upper()
    atr_vals = _atr_series(series, cfg.displacement_atr_period)

    raw_swings = detect_confirmed_swings(
        series,
        exchange=exchange,
        symbol=symbol_u,
        market_type=market_type,
        timeframe=timeframe,
        config=cfg,
    )
    swings = classify_swings(raw_swings)

    unconfirmed: list[SwingPoint] = []
    if include_unconfirmed:
        unconfirmed = detect_unconfirmed_candidates(
            series,
            exchange=exchange,
            symbol=symbol_u,
            market_type=market_type,
            timeframe=timeframe,
            config=cfg,
        )

    bos_events: list[StructureBreak] = []
    choch_events: list[CHoCHEvent] = []
    mss_events: list[MSSEvent] = []
    ambiguous_events: list[AmbiguousDualBreak] = []
    broken_keys: set[str] = set()
    seen_break_keys: set[str] = set()
    directional_break_times: list[tuple[datetime, StructureDirection]] = []

    bias = StructureBias.UNDEFINED

    for i, candle in enumerate(series):
        if not candle.is_closed and cfg.use_closed_candles_only:
            continue

        available = [s for s in swings if s.confirmation_timestamp <= candle.timestamp]
        swing_bias = derive_bias_from_swings(available)
        if bias == StructureBias.UNDEFINED and swing_bias != StructureBias.UNDEFINED:
            bias = swing_bias

        sh = latest_unbroken_swing(available, SwingKind.HIGH, broken_keys)
        sl = latest_unbroken_swing(available, SwingKind.LOW, broken_keys)

        # F5: same-candle dual wick through both levels with close still inside range.
        if sh is not None and sl is not None and sh.price > sl.price:
            wick_above = candle.high > sh.price
            wick_below = candle.low < sl.price
            close_inside = sl.price < candle.close < sh.price
            if wick_above and wick_below and close_inside:
                key = (
                    f"ambiguous_dual_break:{symbol_u}:{timeframe.value}:"
                    f"{format_utc_key(candle.timestamp)}:"
                    f"{format_utc_key(sh.candle_timestamp)}:"
                    f"{format_utc_key(sl.candle_timestamp)}"
                )
                if key not in seen_break_keys:
                    seen_break_keys.add(key)
                    ambiguous_events.append(
                        AmbiguousDualBreak(
                            event_key=key,
                            exchange=exchange,
                            symbol=symbol_u,
                            market_type=market_type,
                            timeframe=timeframe,
                            candle_timestamp=candle.timestamp,
                            confirmation_timestamp=candle.timestamp,
                            close_price=float(candle.close),
                            swing_high_level=sh.price,
                            swing_low_level=sl.price,
                            swing_high_key=sh.event_key,
                            swing_low_key=sl.event_key,
                            high=float(candle.high),
                            low=float(candle.low),
                            bias_unchanged=bias,
                            config_version=cfg.config_version,
                            candle_index=i,
                        )
                    )
                # Deterministic: no directional BOS/CHoCH/MSS and no bias flip.
                continue

        atr_i = float(atr_vals[i]) if i < len(atr_vals) and np.isfinite(atr_vals[i]) else None

        if sh is not None and is_bullish_close_break(candle, sh.price):
            direction = StructureDirection.BULLISH
            kind = classify_break(direction, bias)
            key = break_event_key(
                kind.value,
                direction,
                symbol_u,
                timeframe.value,
                sh.candle_timestamp,
                candle.timestamp,
            )
            if key not in seen_break_keys:
                seen_break_keys.add(key)
                broken_keys.add(sh.event_key)
                prev = bias
                new_bias = bias_after_break(direction, prev, kind)
                body = candle_body(candle)
                br = StructureBreak(
                    event_key=key,
                    exchange=exchange,
                    symbol=symbol_u,
                    market_type=market_type,
                    timeframe=timeframe,
                    break_kind=kind,
                    direction=direction,
                    broken_level=sh.price,
                    broken_swing_key=sh.event_key,
                    broken_swing_timestamp=sh.candle_timestamp,
                    close_price=float(candle.close),
                    candle_timestamp=candle.timestamp,
                    confirmation_timestamp=candle.timestamp,
                    previous_bias=prev,
                    new_bias=new_bias,
                    config_version=cfg.config_version,
                    candle_index=i,
                    body_size=body,
                    atr_value=atr_i,
                )
                directional_break_times.append((candle.timestamp, direction))
                if kind == BreakKind.BOS:
                    bos_events.append(br)
                else:
                    choch = CHoCHEvent(
                        event_key=key,
                        exchange=exchange,
                        symbol=symbol_u,
                        market_type=market_type,
                        timeframe=timeframe,
                        direction=direction,
                        broken_level=sh.price,
                        broken_swing_key=sh.event_key,
                        close_price=float(candle.close),
                        candle_timestamp=candle.timestamp,
                        confirmation_timestamp=candle.timestamp,
                        previous_bias=prev,
                        new_bias=new_bias,
                        config_version=cfg.config_version,
                        structure_break_key=key,
                    )
                    choch_events.append(choch)
                    ok, body_sz, atr_ok = has_displacement(candle, atr_i, cfg)
                    if ok and atr_ok is not None:
                        mss_events.append(
                            build_mss_from_choch(choch, br, candle, body_sz, atr_ok, cfg)
                        )
                bias = new_bias

        # Re-read SL after possible SH break on this candle (non-ambiguous path).
        sl = latest_unbroken_swing(available, SwingKind.LOW, broken_keys)
        if sl is not None and is_bearish_close_break(candle, sl.price):
            direction = StructureDirection.BEARISH
            kind = classify_break(direction, bias)
            key = break_event_key(
                kind.value,
                direction,
                symbol_u,
                timeframe.value,
                sl.candle_timestamp,
                candle.timestamp,
            )
            if key not in seen_break_keys:
                seen_break_keys.add(key)
                broken_keys.add(sl.event_key)
                prev = bias
                new_bias = bias_after_break(direction, prev, kind)
                body = candle_body(candle)
                br = StructureBreak(
                    event_key=key,
                    exchange=exchange,
                    symbol=symbol_u,
                    market_type=market_type,
                    timeframe=timeframe,
                    break_kind=kind,
                    direction=direction,
                    broken_level=sl.price,
                    broken_swing_key=sl.event_key,
                    broken_swing_timestamp=sl.candle_timestamp,
                    close_price=float(candle.close),
                    candle_timestamp=candle.timestamp,
                    confirmation_timestamp=candle.timestamp,
                    previous_bias=prev,
                    new_bias=new_bias,
                    config_version=cfg.config_version,
                    candle_index=i,
                    body_size=body,
                    atr_value=atr_i,
                )
                directional_break_times.append((candle.timestamp, direction))
                if kind == BreakKind.BOS:
                    bos_events.append(br)
                else:
                    choch = CHoCHEvent(
                        event_key=key,
                        exchange=exchange,
                        symbol=symbol_u,
                        market_type=market_type,
                        timeframe=timeframe,
                        direction=direction,
                        broken_level=sl.price,
                        broken_swing_key=sl.event_key,
                        close_price=float(candle.close),
                        candle_timestamp=candle.timestamp,
                        confirmation_timestamp=candle.timestamp,
                        previous_bias=prev,
                        new_bias=new_bias,
                        config_version=cfg.config_version,
                        structure_break_key=key,
                    )
                    choch_events.append(choch)
                    ok, body_sz, atr_ok = has_displacement(candle, atr_i, cfg)
                    if ok and atr_ok is not None:
                        mss_events.append(
                            build_mss_from_choch(choch, br, candle, body_sz, atr_ok, cfg)
                        )
                bias = new_bias

    series_end = series[-1].timestamp if series else None
    # Include CHoCH times as opposing/superseding candidates for BOS segments
    for choch in choch_events:
        directional_break_times.append((choch.candle_timestamp, choch.direction))
    bos_events = _assign_bos_segments(bos_events, directional_break_times, series_end)

    latest_sh = next((s for s in reversed(swings) if s.kind == SwingKind.HIGH), None)
    latest_sl = next((s for s in reversed(swings) if s.kind == SwingKind.LOW), None)
    active_sh = latest_unbroken_swing(swings, SwingKind.HIGH, broken_keys)
    active_sl = latest_unbroken_swing(swings, SwingKind.LOW, broken_keys)

    if bias == StructureBias.UNDEFINED:
        bias = derive_bias_from_swings(swings)

    unbroken_high = active_sh.price if active_sh else None
    unbroken_low = active_sl.price if active_sl else None

    snapshot = MarketStructureSnapshot(
        exchange=exchange,
        symbol=symbol_u,
        market_type=market_type,
        timeframe=timeframe,
        bias=bias,
        latest_swing_high=latest_sh,
        latest_swing_low=latest_sl,
        active_unbroken_swing_high=unbroken_high,
        active_unbroken_swing_low=unbroken_low,
        active_bullish_level=unbroken_high,
        active_bearish_level=unbroken_low,
        last_bos_key=bos_events[-1].event_key if bos_events else None,
        last_choch_key=choch_events[-1].event_key if choch_events else None,
        last_mss_key=mss_events[-1].event_key if mss_events else None,
        last_ambiguous_dual_break_key=(
            ambiguous_events[-1].event_key if ambiguous_events else None
        ),
        closed_candles_used=len(series),
        config_version=cfg.config_version,
        calculated_at=datetime.now(timezone.utc),
    )

    event_keys = (
        [s.event_key for s in swings]
        + [e.event_key for e in bos_events]
        + [e.event_key for e in choch_events]
        + [e.event_key for e in mss_events]
        + [e.event_key for e in ambiguous_events]
    )

    return MarketStructureResult(
        config=cfg.snapshot(),
        snapshot=snapshot,
        swings=swings,
        unconfirmed_swings=unconfirmed,
        bos_events=bos_events,
        choch_events=choch_events,
        mss_events=mss_events,
        ambiguous_dual_breaks=ambiguous_events,
        event_keys=event_keys,
    )


def new_events_since(
    previous_keys: set[str],
    result: MarketStructureResult,
) -> dict[str, list]:
    """Diff helper for realtime: return only events with unseen keys."""
    return {
        "swings": [s for s in result.swings if s.event_key not in previous_keys],
        "bos_events": [e for e in result.bos_events if e.event_key not in previous_keys],
        "choch_events": [e for e in result.choch_events if e.event_key not in previous_keys],
        "mss_events": [e for e in result.mss_events if e.event_key not in previous_keys],
        "ambiguous_dual_breaks": [
            e for e in result.ambiguous_dual_breaks if e.event_key not in previous_keys
        ],
    }
