"""
Technical Indicators calculator.

Deterministic, no look-ahead. Operates on normalized OHLCV candles only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

import numpy as np

from app.analysis.indicators import momentum, moving_averages, volatility, volume
from app.analysis.indicators.models import (
    DEFAULT_INDICATORS,
    INDICATOR_PARAMS,
    WARMUP_REQUIREMENTS,
    CandleFrame,
    IndicatorBundle,
    IndicatorId,
    IndicatorLatest,
    IndicatorPoint,
    IndicatorSeriesResult,
    IndicatorStatus,
)
from app.exchanges.types import Candle


def candles_to_frame(candles: list[Candle], *, include_forming: bool = False) -> CandleFrame:
    """
    Convert candles to a chronological numeric frame.

    By default only closed candles are used (no look-ahead from a forming bar).
    """
    ordered = sorted(candles, key=lambda c: c.timestamp)
    if not include_forming:
        ordered = [c for c in ordered if c.is_closed]

    return CandleFrame(
        timestamps=[c.timestamp for c in ordered],
        open=[c.open for c in ordered],
        high=[c.high for c in ordered],
        low=[c.low for c in ordered],
        close=[c.close for c in ordered],
        volume=[c.volume for c in ordered],
        is_closed=[c.is_closed for c in ordered],
    )


def _status_for(indicator: IndicatorId, samples: int, has_value: bool) -> IndicatorStatus:
    required = WARMUP_REQUIREMENTS[indicator]
    if samples <= 0:
        return IndicatorStatus.INSUFFICIENT_DATA
    if samples < required:
        return IndicatorStatus.WARMING_UP if not has_value else IndicatorStatus.WARMING_UP
    if not has_value:
        return IndicatorStatus.INSUFFICIENT_DATA
    return IndicatorStatus.READY


def _nan_to_none(value: float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (float, int, np.floating)) and not np.isfinite(float(value)):
        return None
    return float(value)


def _series_from_arrays(
    indicator: IndicatorId,
    timestamps: list[datetime],
    is_closed: list[bool],
    field_map: dict[str, np.ndarray],
    samples_used: int,
    *,
    is_forming: bool,
) -> IndicatorSeriesResult:
    params = dict(INDICATOR_PARAMS[indicator])
    warmup = WARMUP_REQUIREMENTS[indicator]
    points: list[IndicatorPoint] = []
    for i, ts in enumerate(timestamps):
        values = {name: _nan_to_none(float(arr[i])) for name, arr in field_map.items()}
        if all(v is None for v in values.values()):
            continue
        points.append(IndicatorPoint(timestamp=ts, values=values, is_closed=is_closed[i]))

    # Latest = last point if any
    latest_fields: dict[str, float | None] = {}
    latest_ts: datetime | None = None
    scalar: float | None = None
    if points:
        latest_ts = points[-1].timestamp
        latest_fields = dict(points[-1].values)
        if "value" in latest_fields:
            scalar = latest_fields["value"]
        elif len(latest_fields) == 1:
            scalar = next(iter(latest_fields.values()))

    has_value = scalar is not None or any(v is not None for v in latest_fields.values())
    status = _status_for(indicator, samples_used, has_value)

    latest = IndicatorLatest(
        status=status,
        is_forming=is_forming and bool(is_closed and not is_closed[-1]) if is_closed else is_forming,
        timestamp=latest_ts,
        warmup_required=warmup,
        samples_used=samples_used,
        params=params,
        value=scalar if "value" in field_map or len(field_map) == 1 else None,
        fields={k: v for k, v in latest_fields.items() if k != "value"} if len(field_map) > 1 else {},
        detail=None
        if status == IndicatorStatus.READY
        else f"Need {warmup} closed candles; have {samples_used}",
    )
    # For multi-field indicators, put components in fields and leave value null unless single.
    if len(field_map) > 1:
        latest.value = None
        latest.fields = latest_fields

    return IndicatorSeriesResult(
        indicator=indicator,
        params=params,
        warmup_required=warmup,
        status=status,
        points=points,
        latest=latest,
    )


def calculate_indicators(
    candles: list[Candle],
    *,
    indicators: Iterable[IndicatorId] | None = None,
    include_forming: bool = False,
    include_series: bool = False,
) -> IndicatorBundle:
    """
    Calculate requested indicators for an OHLCV series.

    Parameters
    ----------
    candles:
        Normalized candles (any order). Sorted ascending internally.
    indicators:
        Subset to calculate. Defaults to all supported indicators.
    include_forming:
        If False (default), forming candles are excluded to avoid look-ahead /
        unstable live distortion in closed-candle analytics.
    include_series:
        If True, attach full timestamp series (heavier). Latest values always returned.
    """
    selected = list(indicators) if indicators is not None else list(DEFAULT_INDICATORS)
    frame = candles_to_frame(candles, include_forming=include_forming)
    samples = frame.size
    forming_included = include_forming and any(not c.is_closed for c in candles)
    is_forming_latest = bool(frame.is_closed and not frame.is_closed[-1]) if frame.size else False

    closes = np.asarray(frame.close, dtype=float)
    highs = np.asarray(frame.high, dtype=float)
    lows = np.asarray(frame.low, dtype=float)
    vols = np.asarray(frame.volume, dtype=float)

    series_out: dict[str, IndicatorSeriesResult] = {}
    latest_out: dict[str, IndicatorLatest] = {}

    def _emit(ind: IndicatorId, field_map: dict[str, np.ndarray]) -> None:
        result = _series_from_arrays(
            ind,
            frame.timestamps,
            frame.is_closed,
            field_map,
            samples,
            is_forming=is_forming_latest,
        )
        if not include_series:
            result.points = []
        series_out[ind.value] = result
        latest_out[ind.value] = result.latest

    for ind in selected:
        if ind in {
            IndicatorId.EMA_9,
            IndicatorId.EMA_20,
            IndicatorId.EMA_50,
            IndicatorId.EMA_100,
            IndicatorId.EMA_200,
        }:
            period = int(INDICATOR_PARAMS[ind]["period"])
            _emit(ind, {"value": moving_averages.ema(closes, period)})
        elif ind in {IndicatorId.SMA_20, IndicatorId.SMA_50, IndicatorId.SMA_200}:
            period = int(INDICATOR_PARAMS[ind]["period"])
            _emit(ind, {"value": moving_averages.sma(closes, period)})
        elif ind == IndicatorId.RSI_14:
            _emit(ind, {"value": momentum.rsi(closes, 14)})
        elif ind == IndicatorId.MACD:
            macd_line, signal, hist = momentum.macd(closes, 12, 26, 9)
            _emit(ind, {"macd": macd_line, "signal": signal, "histogram": hist})
        elif ind == IndicatorId.STOCH_RSI:
            k, d = momentum.stochastic_rsi(closes, 14, 14, 3, 3)
            _emit(ind, {"k": k, "d": d})
        elif ind == IndicatorId.ATR_14:
            _emit(ind, {"value": volatility.atr(highs, lows, closes, 14)})
        elif ind == IndicatorId.BOLLINGER:
            mid, upper, lower = volatility.bollinger_bands(closes, 20, 2.0)
            _emit(ind, {"middle": mid, "upper": upper, "lower": lower})
        elif ind == IndicatorId.VOLUME_SMA_20:
            _emit(ind, {"value": volume.volume_sma(vols, 20)})
        elif ind == IndicatorId.OBV:
            _emit(ind, {"value": volume.obv(closes, vols)})
        elif ind == IndicatorId.RELATIVE_VOLUME:
            _emit(ind, {"value": volume.relative_volume(vols, 20)})

    closed_used = sum(1 for flag in frame.is_closed if flag)
    return IndicatorBundle(
        include_forming=include_forming,
        closed_candles_used=closed_used,
        forming_included=forming_included,
        series=series_out,
        latest=latest_out,
    )


def round_latest_for_api(latest: IndicatorLatest, digits: int = 6) -> IndicatorLatest:
    """Round only at presentation boundary."""

    def _r(v: float | None) -> float | None:
        if v is None:
            return None
        return round(float(v), digits)

    return latest.model_copy(
        update={
            "value": _r(latest.value),
            "fields": {k: _r(v) for k, v in latest.fields.items()},
        }
    )
