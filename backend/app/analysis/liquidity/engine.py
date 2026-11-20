"""Deterministic Liquidity Engine (Phase 3.3)."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from app.analysis.indicators.volatility import atr as wilder_atr
from app.analysis.liquidity.config import DEFAULT_LIQUIDITY_CONFIG, LiquidityConfig
from app.analysis.liquidity.eq_cluster import cluster_equal_extremes
from app.analysis.liquidity.models import (
    AmbiguousLiquidityCross,
    LiquidityLevel,
    LiquidityResult,
    LiquiditySnapshot,
    LiquiditySourceType,
    LiquidityStatus,
    LiquiditySweep,
    LiquidityType,
    ReactionHint,
    SweepDirection,
    SwingContribution,
)
from app.analysis.liquidity.tolerance import penetration_distance
from app.analysis.market_structure import analyze_market_structure
from app.analysis.market_structure.config import DEFAULT_STRUCTURE_CONFIG
from app.analysis.market_structure.models import SwingKind, SwingPoint
from app.analysis.market_structure.timestamps import ensure_utc
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


def _index_by_timestamp(candles: list[Candle]) -> dict[datetime, int]:
    mapping: dict[datetime, int] = {}
    for i, c in enumerate(candles):
        ts = ensure_utc(c.timestamp, field="timestamp")
        mapping[ts] = i
    return mapping


def _swing_level_key(
    liquidity_type: LiquidityType,
    source: LiquiditySourceType,
    swing_or_cluster_key: str,
) -> str:
    return f"liq:{liquidity_type.value}:{source.value}:{swing_or_cluster_key}"


def _build_levels_from_swings(
    *,
    swings: list[SwingPoint],
    eqh: list,
    eql: list,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    timeframe: Timeframe,
    cfg: LiquidityConfig,
    series_end: datetime | None,
) -> tuple[list[LiquidityLevel], list[LiquidityLevel]]:
    symbol_u = symbol.upper()
    eqh_keys = {m.swing_key for c in eqh for m in c.members}
    eql_keys = {m.swing_key for c in eql for m in c.members}

    bsl: list[LiquidityLevel] = []
    ssl: list[LiquidityLevel] = []

    for cluster in eqh:
        key = _swing_level_key(LiquidityType.BSL, LiquiditySourceType.EQH, cluster.event_key)
        bsl.append(
            LiquidityLevel(
                event_key=key,
                exchange=exchange,
                symbol=symbol_u,
                market_type=market_type,
                timeframe=timeframe,
                liquidity_type=LiquidityType.BSL,
                source_type=LiquiditySourceType.EQH,
                price=cluster.level,
                status=LiquidityStatus.ACTIVE,
                source_swing_keys=[m.swing_key for m in cluster.members],
                source_swings=list(cluster.members),
                cluster_key=cluster.event_key,
                detection_timestamp=cluster.first_detection_timestamp,
                latest_confirmation_timestamp=cluster.latest_confirmation_timestamp,
                config_version=cfg.config_version,
                segment_start=cluster.first_detection_timestamp,
                segment_end=series_end,
                segment_active=True,
            )
        )

    for cluster in eql:
        key = _swing_level_key(LiquidityType.SSL, LiquiditySourceType.EQL, cluster.event_key)
        ssl.append(
            LiquidityLevel(
                event_key=key,
                exchange=exchange,
                symbol=symbol_u,
                market_type=market_type,
                timeframe=timeframe,
                liquidity_type=LiquidityType.SSL,
                source_type=LiquiditySourceType.EQL,
                price=cluster.level,
                status=LiquidityStatus.ACTIVE,
                source_swing_keys=[m.swing_key for m in cluster.members],
                source_swings=list(cluster.members),
                cluster_key=cluster.event_key,
                detection_timestamp=cluster.first_detection_timestamp,
                latest_confirmation_timestamp=cluster.latest_confirmation_timestamp,
                config_version=cfg.config_version,
                segment_start=cluster.first_detection_timestamp,
                segment_end=series_end,
                segment_active=True,
            )
        )

    for swing in swings:
        if not swing.confirmed:
            continue
        conf = ensure_utc(swing.confirmation_timestamp, field="confirmation_timestamp")
        contrib = SwingContribution(
            swing_key=swing.event_key,
            price=float(swing.price),
            candle_timestamp=ensure_utc(swing.candle_timestamp, field="candle_timestamp"),
            confirmation_timestamp=conf,
        )
        if swing.kind == SwingKind.HIGH and swing.event_key not in eqh_keys:
            key = _swing_level_key(LiquidityType.BSL, LiquiditySourceType.SWING, swing.event_key)
            bsl.append(
                LiquidityLevel(
                    event_key=key,
                    exchange=exchange,
                    symbol=symbol_u,
                    market_type=market_type,
                    timeframe=timeframe,
                    liquidity_type=LiquidityType.BSL,
                    source_type=LiquiditySourceType.SWING,
                    price=float(swing.price),
                    status=LiquidityStatus.ACTIVE,
                    source_swing_keys=[swing.event_key],
                    source_swings=[contrib],
                    cluster_key=None,
                    detection_timestamp=conf,
                    latest_confirmation_timestamp=conf,
                    config_version=cfg.config_version,
                    segment_start=conf,
                    segment_end=series_end,
                    segment_active=True,
                )
            )
        elif swing.kind == SwingKind.LOW and swing.event_key not in eql_keys:
            key = _swing_level_key(LiquidityType.SSL, LiquiditySourceType.SWING, swing.event_key)
            ssl.append(
                LiquidityLevel(
                    event_key=key,
                    exchange=exchange,
                    symbol=symbol_u,
                    market_type=market_type,
                    timeframe=timeframe,
                    liquidity_type=LiquidityType.SSL,
                    source_type=LiquiditySourceType.SWING,
                    price=float(swing.price),
                    status=LiquidityStatus.ACTIVE,
                    source_swing_keys=[swing.event_key],
                    source_swings=[contrib],
                    cluster_key=None,
                    detection_timestamp=conf,
                    latest_confirmation_timestamp=conf,
                    config_version=cfg.config_version,
                    segment_start=conf,
                    segment_end=series_end,
                    segment_active=True,
                )
            )

    bsl.sort(key=lambda x: (x.detection_timestamp, x.event_key))
    ssl.sort(key=lambda x: (x.detection_timestamp, x.event_key))
    return bsl, ssl


def analyze_liquidity(
    candles: list[Candle],
    *,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    timeframe: Timeframe,
    config: LiquidityConfig | None = None,
    swings: list[SwingPoint] | None = None,
    include_unconfirmed: bool = False,
) -> LiquidityResult:
    """
    Run deterministic liquidity analysis.

    Confirmed events use closed candles only. Forming-candle sweeps are provisional
    and returned separately when include_unconfirmed=True.
    """
    cfg = config or DEFAULT_LIQUIDITY_CONFIG
    symbol_u = symbol.upper()

    for i, c in enumerate(candles):
        ensure_utc(c.timestamp, field=f"candles[{i}].timestamp")

    closed = [c for c in candles if c.is_closed] if cfg.use_closed_candles_only else list(candles)
    forming = None
    if include_unconfirmed and candles and not candles[-1].is_closed:
        forming = candles[-1]

    if swings is None:
        ms = analyze_market_structure(
            candles,
            exchange=exchange,
            symbol=symbol_u,
            market_type=market_type,
            timeframe=timeframe,
            config=DEFAULT_STRUCTURE_CONFIG,
            include_unconfirmed=False,
        )
        swings = list(ms.swings)

    atr_vals = _atr_series(closed if closed else candles, cfg.atr_period)
    # Align ATR length with closed series used for indexing
    atr_source = closed if closed else candles
    idx_map = _index_by_timestamp(atr_source)
    series_end = (
        ensure_utc(closed[-1].timestamp, field="timestamp") if closed else None
    )

    # Final clusters from all confirmed swings (as of series end)
    as_of = series_end
    eqh = cluster_equal_extremes(
        swings,
        kind=SwingKind.HIGH,
        exchange=exchange,
        symbol=symbol_u,
        market_type=market_type,
        timeframe=timeframe,
        atr_by_index=atr_vals,
        index_by_confirm_ts=idx_map,
        cfg=cfg,
        as_of=as_of,
    )
    eql = cluster_equal_extremes(
        swings,
        kind=SwingKind.LOW,
        exchange=exchange,
        symbol=symbol_u,
        market_type=market_type,
        timeframe=timeframe,
        atr_by_index=atr_vals,
        index_by_confirm_ts=idx_map,
        cfg=cfg,
        as_of=as_of,
    )

    bsl_levels, ssl_levels = _build_levels_from_swings(
        swings=swings,
        eqh=eqh,
        eql=eql,
        exchange=exchange,
        symbol=symbol_u,
        market_type=market_type,
        timeframe=timeframe,
        cfg=cfg,
        series_end=series_end,
    )

    # Mutable status maps for chronological sweep/break scan
    level_by_key: dict[str, LiquidityLevel] = {
        lv.event_key: lv for lv in bsl_levels + ssl_levels
    }
    sweeps: list[LiquiditySweep] = []
    ambiguous: list[AmbiguousLiquidityCross] = []
    seen_sweep_keys: set[str] = set()

    def active_levels(liq_type: LiquidityType, at: datetime) -> list[LiquidityLevel]:
        out: list[LiquidityLevel] = []
        for lv in level_by_key.values():
            if lv.liquidity_type != liq_type:
                continue
            if lv.status != LiquidityStatus.ACTIVE:
                continue
            if lv.detection_timestamp > at:
                continue
            out.append(lv)
        return out

    def process_candle(candle: Candle, index: int, *, confirmed: bool) -> None:
        ts = ensure_utc(candle.timestamp, field="timestamp")
        atr_i = atr_vals[index] if 0 <= index < len(atr_vals) else None
        act_bsl = active_levels(LiquidityType.BSL, ts)
        act_ssl = active_levels(LiquidityType.SSL, ts)

        crossed_bsl = [
            lv
            for lv in act_bsl
            if float(candle.high)
            >= float(lv.price) + penetration_distance(lv.price, atr_i, cfg)
        ]
        crossed_ssl = [
            lv
            for lv in act_ssl
            if float(candle.low)
            <= float(lv.price) - penetration_distance(lv.price, atr_i, cfg)
        ]

        if crossed_bsl and crossed_ssl:
            amb_key = (
                f"liq:ambiguous:{exchange.value}:{market_type.value}:{symbol_u}:"
                f"{timeframe.value}:{ts.strftime('%Y%m%dT%H%M%SZ')}"
            )
            if amb_key not in seen_sweep_keys:
                seen_sweep_keys.add(amb_key)
                ambiguous.append(
                    AmbiguousLiquidityCross(
                        event_key=amb_key,
                        exchange=exchange,
                        symbol=symbol_u,
                        market_type=market_type,
                        timeframe=timeframe,
                        candle_timestamp=ts,
                        confirmation_timestamp=ts,
                        close_price=float(candle.close),
                        high=float(candle.high),
                        low=float(candle.low),
                        bsl_level_keys=[lv.event_key for lv in crossed_bsl],
                        ssl_level_keys=[lv.event_key for lv in crossed_ssl],
                        config_version=cfg.config_version,
                    )
                )
            return

        for lv in crossed_bsl:
            pen = penetration_distance(lv.price, atr_i, cfg)
            if float(candle.close) < float(lv.price):
                # Sweep
                sk = (
                    f"liq:sweep:bsl:{lv.event_key}:"
                    f"{ts.strftime('%Y%m%dT%H%M%SZ')}"
                )
                if sk in seen_sweep_keys:
                    continue
                seen_sweep_keys.add(sk)
                sweeps.append(
                    LiquiditySweep(
                        event_key=sk,
                        exchange=exchange,
                        symbol=symbol_u,
                        market_type=market_type,
                        timeframe=timeframe,
                        # Deprecated side label (BSL → bullish_side historically).
                        direction=SweepDirection.BULLISH_SIDE,
                        # Contextual ICT reaction — NOT a trade signal.
                        reaction_hint=ReactionHint.BEARISH,
                        liquidity_level_key=lv.event_key,
                        liquidity_type=LiquidityType.BSL,
                        level_price=float(lv.price),
                        wick_extreme=float(candle.high),
                        close_price=float(candle.close),
                        penetration=pen,
                        candle_timestamp=ts,
                        confirmation_timestamp=ts,
                        confirmed=confirmed,
                        config_version=cfg.config_version,
                        candle_index=index,
                    )
                )
                if confirmed:
                    lv.status = LiquidityStatus.SWEPT
                    lv.status_changed_timestamp = ts
                    lv.segment_end = ts
                    lv.segment_active = False
            elif float(candle.close) > float(lv.price):
                if confirmed:
                    lv.status = LiquidityStatus.BROKEN
                    lv.status_changed_timestamp = ts
                    lv.segment_end = ts
                    lv.segment_active = False

        for lv in crossed_ssl:
            pen = penetration_distance(lv.price, atr_i, cfg)
            if float(candle.close) > float(lv.price):
                sk = (
                    f"liq:sweep:ssl:{lv.event_key}:"
                    f"{ts.strftime('%Y%m%dT%H%M%SZ')}"
                )
                if sk in seen_sweep_keys:
                    continue
                seen_sweep_keys.add(sk)
                sweeps.append(
                    LiquiditySweep(
                        event_key=sk,
                        exchange=exchange,
                        symbol=symbol_u,
                        market_type=market_type,
                        timeframe=timeframe,
                        # Deprecated side label (SSL → bearish_side historically).
                        direction=SweepDirection.BEARISH_SIDE,
                        # Contextual ICT reaction — NOT a trade signal.
                        reaction_hint=ReactionHint.BULLISH,
                        liquidity_level_key=lv.event_key,
                        liquidity_type=LiquidityType.SSL,
                        level_price=float(lv.price),
                        wick_extreme=float(candle.low),
                        close_price=float(candle.close),
                        penetration=pen,
                        candle_timestamp=ts,
                        confirmation_timestamp=ts,
                        confirmed=confirmed,
                        config_version=cfg.config_version,
                        candle_index=index,
                    )
                )
                if confirmed:
                    lv.status = LiquidityStatus.SWEPT
                    lv.status_changed_timestamp = ts
                    lv.segment_end = ts
                    lv.segment_active = False
            elif float(candle.close) < float(lv.price):
                if confirmed:
                    lv.status = LiquidityStatus.BROKEN
                    lv.status_changed_timestamp = ts
                    lv.segment_end = ts
                    lv.segment_active = False

    for i, candle in enumerate(atr_source):
        if cfg.use_closed_candles_only and not candle.is_closed:
            continue
        process_candle(candle, i, confirmed=True)

    provisional: list[LiquiditySweep] = []
    if forming is not None and include_unconfirmed:
        # Index against full candles list for ATR — use last closed ATR if forming
        form_idx = len(atr_source) - 1 if atr_source else -1
        before = len(sweeps)
        process_candle(forming, max(form_idx, 0), confirmed=False)
        provisional = [s for s in sweeps[before:] if not s.confirmed]
        sweeps = [s for s in sweeps if s.confirmed]

    # Refresh level lists from mutated map (stable order)
    bsl_final = sorted(
        [lv for lv in level_by_key.values() if lv.liquidity_type == LiquidityType.BSL],
        key=lambda x: (x.detection_timestamp, x.event_key),
    )
    ssl_final = sorted(
        [lv for lv in level_by_key.values() if lv.liquidity_type == LiquidityType.SSL],
        key=lambda x: (x.detection_timestamp, x.event_key),
    )

    now = datetime.now(timezone.utc)
    event_keys = (
        [c.event_key for c in eqh]
        + [c.event_key for c in eql]
        + [lv.event_key for lv in bsl_final]
        + [lv.event_key for lv in ssl_final]
        + [s.event_key for s in sweeps]
        + [a.event_key for a in ambiguous]
    )

    snapshot = LiquiditySnapshot(
        exchange=exchange,
        symbol=symbol_u,
        market_type=market_type,
        timeframe=timeframe,
        calculated_at=now,
        config_version=cfg.config_version,
        closed_candles_used=len(closed),
        active_bsl_count=sum(1 for lv in bsl_final if lv.status == LiquidityStatus.ACTIVE),
        active_ssl_count=sum(1 for lv in ssl_final if lv.status == LiquidityStatus.ACTIVE),
        eqh_count=len(eqh),
        eql_count=len(eql),
        sweep_count=len(sweeps),
        candle_range_start=ensure_utc(candles[0].timestamp, field="timestamp")
        if candles
        else None,
        candle_range_end=ensure_utc(candles[-1].timestamp, field="timestamp")
        if candles
        else None,
    )

    return LiquidityResult(
        config=cfg.snapshot(),
        snapshot=snapshot,
        eqh_clusters=eqh,
        eql_clusters=eql,
        bsl_levels=bsl_final,
        ssl_levels=ssl_final,
        sweeps=sweeps,
        provisional_sweeps=provisional,
        ambiguous_crosses=ambiguous,
        event_keys=event_keys,
    )


def new_liquidity_events_since(
    result: LiquidityResult,
    previous_keys: set[str],
) -> dict[str, list]:
    """Diff helper for WS — only previously unseen keys."""
    return {
        "eqh_clusters": [e for e in result.eqh_clusters if e.event_key not in previous_keys],
        "eql_clusters": [e for e in result.eql_clusters if e.event_key not in previous_keys],
        "bsl_levels": [e for e in result.bsl_levels if e.event_key not in previous_keys],
        "ssl_levels": [e for e in result.ssl_levels if e.event_key not in previous_keys],
        "sweeps": [e for e in result.sweeps if e.event_key not in previous_keys],
        "ambiguous_crosses": [
            e for e in result.ambiguous_crosses if e.event_key not in previous_keys
        ],
    }
