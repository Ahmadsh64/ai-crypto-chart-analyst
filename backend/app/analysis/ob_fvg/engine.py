"""Deterministic Order Block & FVG engine (Phase 3.4)."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from app.analysis.indicators.volatility import atr as wilder_atr
from app.analysis.market_structure import analyze_market_structure
from app.analysis.market_structure.config import DEFAULT_STRUCTURE_CONFIG
from app.analysis.market_structure.models import (
    BreakKind,
    MSSEvent,
    StructureBreak,
    StructureDirection,
)
from app.analysis.market_structure.timestamps import ensure_utc
from app.analysis.ob_fvg.config import DEFAULT_OB_FVG_CONFIG, ObFvgConfig
from app.analysis.ob_fvg.models import (
    FairValueGap,
    FvgStatus,
    ObFvgResult,
    ObFvgSnapshot,
    ObStatus,
    OrderBlock,
    StructureSourceKind,
    ZoneSide,
)
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe


def _atr_series(candles: list[Candle], period: int) -> list[float | None]:
    if not candles:
        return []
    high = np.array([c.high for c in candles], dtype=float)
    low = np.array([c.low for c in candles], dtype=float)
    close = np.array([c.close for c in candles], dtype=float)
    raw = wilder_atr(high, low, close, period=period)
    out: list[float | None] = []
    for v in raw:
        if v is None or (isinstance(v, float) and (np.isnan(v) or not np.isfinite(v))):
            out.append(None)
        else:
            out.append(float(v))
    return out


def _is_bearish(c: Candle) -> bool:
    return float(c.close) < float(c.open)


def _is_bullish(c: Candle) -> bool:
    return float(c.close) > float(c.open)


def _body(c: Candle) -> float:
    return abs(float(c.close) - float(c.open))


def _overlaps(c: Candle, lo: float, hi: float) -> bool:
    return float(c.high) >= lo and float(c.low) <= hi


def _full_traverse(c: Candle, lo: float, hi: float) -> bool:
    return float(c.high) >= hi and float(c.low) <= lo


def _fill_pct(c: Candle, lo: float, hi: float) -> float:
    width = hi - lo
    if width <= 0:
        return 0.0
    overlap_lo = max(float(c.low), lo)
    overlap_hi = min(float(c.high), hi)
    if overlap_hi <= overlap_lo:
        return 0.0
    return min(100.0, 100.0 * (overlap_hi - overlap_lo) / width)


def _ob_key(side: ZoneSide, structure_key: str, source_ts: datetime) -> str:
    return (
        f"ob:{side.value}:{structure_key}:"
        f"{source_ts.strftime('%Y%m%dT%H%M%SZ')}"
    )


def _fvg_key(
    side: ZoneSide,
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    timeframe: Timeframe,
    c3_ts: datetime,
) -> str:
    return (
        f"fvg:{side.value}:{exchange.value}:{market_type.value}:"
        f"{symbol.upper()}:{timeframe.value}:{c3_ts.strftime('%Y%m%dT%H%M%SZ')}"
    )


def _find_opposing_candle(
    candles: list[Candle],
    break_index: int,
    *,
    want_bearish: bool,
    max_lookback: int,
) -> Candle | None:
    start = break_index - 1
    end = max(-1, break_index - 1 - max_lookback)
    for j in range(start, end, -1):
        if j < 0:
            break
        c = candles[j]
        if want_bearish and _is_bearish(c):
            return c
        if not want_bearish and _is_bullish(c):
            return c
    return None


def _apply_ob_lifecycle(
    ob: OrderBlock,
    candles: list[Candle],
    start_index: int,
) -> None:
    for c in candles[start_index:]:
        if not c.is_closed:
            continue
        ts = ensure_utc(c.timestamp, field="timestamp")
        if ts < ob.detection_timestamp:
            continue
        if ob.status in (ObStatus.MITIGATED, ObStatus.INVALIDATED):
            break

        lo, hi = float(ob.zone_low), float(ob.zone_high)

        if _full_traverse(c, lo, hi):
            if ob.status == ObStatus.ACTIVE:
                ob.first_mitigation_timestamp = ts
            ob.status = ObStatus.MITIGATED
            ob.full_mitigation_timestamp = ts
            ob.segment_end = ts
            ob.segment_active = False
            break

        if ob.status == ObStatus.ACTIVE and _overlaps(c, lo, hi):
            ob.status = ObStatus.PARTIALLY_MITIGATED
            ob.first_mitigation_timestamp = ts

        # Invalidation only if not mitigated
        if ob.status != ObStatus.MITIGATED:
            if ob.side == ZoneSide.BULLISH and float(c.close) < lo:
                ob.status = ObStatus.INVALIDATED
                ob.invalidation_timestamp = ts
                ob.segment_end = ts
                ob.segment_active = False
                break
            if ob.side == ZoneSide.BEARISH and float(c.close) > hi:
                ob.status = ObStatus.INVALIDATED
                ob.invalidation_timestamp = ts
                ob.segment_end = ts
                ob.segment_active = False
                break


def _apply_fvg_lifecycle(
    fvg: FairValueGap,
    candles: list[Candle],
    start_index: int,
) -> None:
    for c in candles[start_index:]:
        if not c.is_closed:
            continue
        ts = ensure_utc(c.timestamp, field="timestamp")
        if ts <= fvg.detection_timestamp:
            # Lifecycle starts on candles *after* the FVG forms (c3 is detection).
            continue
        if fvg.status in (FvgStatus.FILLED, FvgStatus.INVALIDATED):
            break

        lo, hi = float(fvg.zone_low), float(fvg.zone_high)
        pct = _fill_pct(c, lo, hi)
        if pct > fvg.max_fill_pct:
            fvg.max_fill_pct = pct

        if _full_traverse(c, lo, hi):
            if fvg.status == FvgStatus.ACTIVE:
                fvg.first_touch_timestamp = ts
            fvg.status = FvgStatus.FILLED
            fvg.full_fill_timestamp = ts
            fvg.max_fill_pct = 100.0
            fvg.segment_end = ts
            fvg.segment_active = False
            break

        if fvg.status == FvgStatus.ACTIVE and _overlaps(c, lo, hi):
            fvg.status = FvgStatus.PARTIALLY_FILLED
            fvg.first_touch_timestamp = ts

        # Far-boundary invalidation (fill approach side):
        # bullish FVG — close below zone_low; bearish FVG — close above zone_high.
        if fvg.status != FvgStatus.FILLED:
            if fvg.side == ZoneSide.BULLISH and float(c.close) < lo:
                fvg.status = FvgStatus.INVALIDATED
                fvg.invalidation_timestamp = ts
                fvg.segment_end = ts
                fvg.segment_active = False
                break
            if fvg.side == ZoneSide.BEARISH and float(c.close) > hi:
                fvg.status = FvgStatus.INVALIDATED
                fvg.invalidation_timestamp = ts
                fvg.segment_end = ts
                fvg.segment_active = False
                break


def _detect_order_blocks(
    closed: list[Candle],
    atr_vals: list[float | None],
    *,
    bos_events: list[StructureBreak],
    mss_events: list[MSSEvent],
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    timeframe: Timeframe,
    cfg: ObFvgConfig,
    series_end: datetime | None,
) -> list[OrderBlock]:
    symbol_u = symbol.upper()
    idx_by_ts = {
        ensure_utc(c.timestamp, field="timestamp"): i for i, c in enumerate(closed)
    }
    out: list[OrderBlock] = []
    seen: set[str] = set()

    structure_items: list[tuple[StructureSourceKind, str, StructureDirection, datetime, int]] = []

    for bos in bos_events:
        if bos.break_kind != BreakKind.BOS:
            continue
        ts = ensure_utc(bos.candle_timestamp, field="candle_timestamp")
        idx = bos.candle_index if 0 <= bos.candle_index < len(closed) else idx_by_ts.get(ts)
        if idx is None:
            continue
        structure_items.append(
            (StructureSourceKind.BOS, bos.event_key, bos.direction, ts, idx)
        )

    for mss in mss_events:
        ts = ensure_utc(mss.candle_timestamp, field="candle_timestamp")
        idx = idx_by_ts.get(ts)
        if idx is None:
            # MSS may share candle with CHoCH — locate by timestamp only
            continue
        structure_items.append(
            (StructureSourceKind.MSS, mss.event_key, mss.direction, ts, idx)
        )

    structure_items.sort(key=lambda x: (x[3], x[1]))

    for kind, event_key, direction, break_ts, break_idx in structure_items:
        if break_idx < 0 or break_idx >= len(closed):
            continue
        atr_i = atr_vals[break_idx] if break_idx < len(atr_vals) else None
        if atr_i is None or atr_i <= 0:
            continue
        break_candle = closed[break_idx]
        if _body(break_candle) < cfg.ob_displacement_atr_mult * atr_i:
            continue

        bullish = direction == StructureDirection.BULLISH
        source = _find_opposing_candle(
            closed,
            break_idx,
            want_bearish=bullish,
            max_lookback=cfg.ob_max_lookback,
        )
        if source is None:
            continue
        source_ts = ensure_utc(source.timestamp, field="timestamp")
        if source_ts >= break_ts:
            continue

        zone_low = float(source.low)
        zone_high = float(source.high)
        if zone_high <= zone_low:
            continue

        side = ZoneSide.BULLISH if bullish else ZoneSide.BEARISH
        key = _ob_key(side, event_key, source_ts)
        if key in seen:
            continue
        seen.add(key)

        detection = ensure_utc(
            break_candle.timestamp, field="timestamp"
        )
        ob = OrderBlock(
            event_key=key,
            exchange=exchange,
            symbol=symbol_u,
            market_type=market_type,
            timeframe=timeframe,
            side=side,
            status=ObStatus.ACTIVE,
            zone_low=zone_low,
            zone_high=zone_high,
            boundary_method=cfg.ob_boundary_method,
            source_candle_timestamp=source_ts,
            source_open=float(source.open),
            source_high=float(source.high),
            source_low=float(source.low),
            source_close=float(source.close),
            source_structure_kind=kind,
            source_structure_event_key=event_key,
            structure_candle_timestamp=break_ts,
            detection_timestamp=detection,
            config_version=cfg.config_version,
            confirmed=True,
            segment_start=detection,
            segment_end=series_end,
            segment_active=True,
        )
        _apply_ob_lifecycle(ob, closed, break_idx + 1)
        if ob.segment_active and series_end is not None:
            ob.segment_end = series_end
        out.append(ob)

    out.sort(key=lambda o: (o.detection_timestamp, o.event_key))
    return out


def _detect_fvgs(
    closed: list[Candle],
    atr_vals: list[float | None],
    *,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    timeframe: Timeframe,
    cfg: ObFvgConfig,
    series_end: datetime | None,
    confirmed: bool = True,
) -> list[FairValueGap]:
    symbol_u = symbol.upper()
    out: list[FairValueGap] = []
    seen: set[str] = set()

    for i in range(2, len(closed)):
        c1, c2, c3 = closed[i - 2], closed[i - 1], closed[i]
        if confirmed and cfg.use_closed_candles_only and not (
            c1.is_closed and c2.is_closed and c3.is_closed
        ):
            continue
        if not confirmed and not (c1.is_closed and c2.is_closed and not c3.is_closed):
            # Provisional only when c3 is the forming candle.
            continue

        atr_i = atr_vals[i] if i < len(atr_vals) else None
        mid_ref = (float(c1.high) + float(c3.low)) / 2.0
        min_gap = (
            cfg.fvg_min_gap_atr_mult * atr_i
            if atr_i is not None and atr_i > 0
            else cfg.fvg_min_gap_fallback_pct * abs(mid_ref)
        )

        candidates: list[tuple[ZoneSide, float, float, float]] = []
        # bullish
        if float(c3.low) > float(c1.high):
            gap = float(c3.low) - float(c1.high)
            if gap >= min_gap and gap > 0:
                candidates.append((ZoneSide.BULLISH, float(c1.high), float(c3.low), gap))
        # bearish
        if float(c3.high) < float(c1.low):
            gap = float(c1.low) - float(c3.high)
            if gap >= min_gap and gap > 0:
                candidates.append((ZoneSide.BEARISH, float(c3.high), float(c1.low), gap))

        c3_ts = ensure_utc(c3.timestamp, field="timestamp")
        for side, lo, hi, gap in candidates:
            if hi <= lo:
                continue
            key = _fvg_key(side, exchange, market_type, symbol_u, timeframe, c3_ts)
            if key in seen:
                continue
            seen.add(key)
            fvg = FairValueGap(
                event_key=key,
                exchange=exchange,
                symbol=symbol_u,
                market_type=market_type,
                timeframe=timeframe,
                side=side,
                status=FvgStatus.ACTIVE,
                zone_low=lo,
                zone_high=hi,
                gap_size=gap,
                candle1_timestamp=ensure_utc(c1.timestamp, field="timestamp"),
                candle2_timestamp=ensure_utc(c2.timestamp, field="timestamp"),
                candle3_timestamp=c3_ts,
                candle1_high=float(c1.high),
                candle1_low=float(c1.low),
                candle3_high=float(c3.high),
                candle3_low=float(c3.low),
                detection_timestamp=c3_ts,
                config_version=cfg.config_version,
                confirmed=confirmed,
                segment_start=c3_ts,
                segment_end=series_end,
                segment_active=True,
            )
            if confirmed:
                _apply_fvg_lifecycle(fvg, closed, i + 1)
                if fvg.segment_active and series_end is not None:
                    fvg.segment_end = series_end
            out.append(fvg)

    out.sort(key=lambda f: (f.detection_timestamp, f.event_key))
    return out


def analyze_ob_fvg(
    candles: list[Candle],
    *,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    timeframe: Timeframe,
    config: ObFvgConfig | None = None,
    bos_events: list[StructureBreak] | None = None,
    mss_events: list[MSSEvent] | None = None,
    include_unconfirmed: bool = False,
) -> ObFvgResult:
    """Run deterministic OB + FVG analysis. Confirmed events use closed candles only."""
    cfg = config or DEFAULT_OB_FVG_CONFIG
    symbol_u = symbol.upper()

    for i, c in enumerate(candles):
        ensure_utc(c.timestamp, field=f"candles[{i}].timestamp")

    closed = [c for c in candles if c.is_closed] if cfg.use_closed_candles_only else list(candles)
    forming = candles[-1] if candles and not candles[-1].is_closed else None

    if bos_events is None or mss_events is None:
        ms = analyze_market_structure(
            candles,
            exchange=exchange,
            symbol=symbol_u,
            market_type=market_type,
            timeframe=timeframe,
            config=DEFAULT_STRUCTURE_CONFIG,
            include_unconfirmed=False,
        )
        bos_events = list(ms.bos_events) if bos_events is None else bos_events
        mss_events = list(ms.mss_events) if mss_events is None else mss_events

    atr_vals = _atr_series(closed, cfg.atr_period)
    series_end = (
        ensure_utc(closed[-1].timestamp, field="timestamp") if closed else None
    )

    order_blocks = _detect_order_blocks(
        closed,
        atr_vals,
        bos_events=bos_events,
        mss_events=mss_events,
        exchange=exchange,
        symbol=symbol_u,
        market_type=market_type,
        timeframe=timeframe,
        cfg=cfg,
        series_end=series_end,
    )
    fvgs = _detect_fvgs(
        closed,
        atr_vals,
        exchange=exchange,
        symbol=symbol_u,
        market_type=market_type,
        timeframe=timeframe,
        cfg=cfg,
        series_end=series_end,
        confirmed=True,
    )

    provisional_obs: list[OrderBlock] = []
    provisional_fvgs: list[FairValueGap] = []
    if include_unconfirmed and forming is not None and closed:
        # Provisional FVG only: forming candle as c3 with last two closed.
        if len(closed) >= 2:
            probe = closed[-2:] + [forming]
            atr_probe = _atr_series(closed, cfg.atr_period)
            # Use last closed ATR for gap threshold
            atr_ext = list(atr_probe) + [atr_probe[-1] if atr_probe else None]
            provisional_fvgs = _detect_fvgs(
                probe,
                atr_ext,
                exchange=exchange,
                symbol=symbol_u,
                market_type=market_type,
                timeframe=timeframe,
                cfg=cfg,
                series_end=None,
                confirmed=False,
            )
            provisional_fvgs = [f for f in provisional_fvgs if not f.confirmed]

    bull_ob = [o for o in order_blocks if o.side == ZoneSide.BULLISH]
    bear_ob = [o for o in order_blocks if o.side == ZoneSide.BEARISH]
    bull_fvg = [f for f in fvgs if f.side == ZoneSide.BULLISH]
    bear_fvg = [f for f in fvgs if f.side == ZoneSide.BEARISH]

    now = datetime.now(timezone.utc)
    event_keys = (
        [o.event_key for o in order_blocks]
        + [f.event_key for f in fvgs]
    )

    snapshot = ObFvgSnapshot(
        exchange=exchange,
        symbol=symbol_u,
        market_type=market_type,
        timeframe=timeframe,
        calculated_at=now,
        config_version=cfg.config_version,
        closed_candles_used=len(closed),
        active_ob_count=sum(1 for o in order_blocks if o.status == ObStatus.ACTIVE),
        active_fvg_count=sum(1 for f in fvgs if f.status == FvgStatus.ACTIVE),
        bullish_ob_count=len(bull_ob),
        bearish_ob_count=len(bear_ob),
        bullish_fvg_count=len(bull_fvg),
        bearish_fvg_count=len(bear_fvg),
        candle_range_start=ensure_utc(candles[0].timestamp, field="timestamp")
        if candles
        else None,
        candle_range_end=ensure_utc(candles[-1].timestamp, field="timestamp")
        if candles
        else None,
    )

    return ObFvgResult(
        config=cfg.snapshot(),
        snapshot=snapshot,
        bullish_order_blocks=bull_ob,
        bearish_order_blocks=bear_ob,
        bullish_fvgs=bull_fvg,
        bearish_fvgs=bear_fvg,
        provisional_order_blocks=provisional_obs,
        provisional_fvgs=provisional_fvgs,
        event_keys=event_keys,
    )


def new_ob_fvg_events_since(
    result: ObFvgResult,
    previous_keys: set[str],
) -> dict[str, list]:
    return {
        "bullish_order_blocks": [
            e for e in result.bullish_order_blocks if e.event_key not in previous_keys
        ],
        "bearish_order_blocks": [
            e for e in result.bearish_order_blocks if e.event_key not in previous_keys
        ],
        "bullish_fvgs": [
            e for e in result.bullish_fvgs if e.event_key not in previous_keys
        ],
        "bearish_fvgs": [
            e for e in result.bearish_fvgs if e.event_key not in previous_keys
        ],
    }
