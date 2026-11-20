"""Deterministic unit tests for the technical indicators engine (no live exchange)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.analysis.indicators.calculator import calculate_indicators, candles_to_frame
from app.analysis.indicators.models import IndicatorId, IndicatorStatus
from app.analysis.indicators import momentum, moving_averages, volatility, volume
from app.exchanges.types import Candle, ExchangeId, MarketType


def _ts(i: int) -> datetime:
    return datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15 * i)


def make_candles(
    closes: list[float],
    *,
    volumes: list[float] | None = None,
    forming_last: bool = False,
) -> list[Candle]:
    vols = volumes or [100.0 + (i % 5) for i in range(len(closes))]
    out: list[Candle] = []
    for i, close in enumerate(closes):
        high = close + 1.0
        low = close - 1.0
        open_ = closes[i - 1] if i else close
        out.append(
            Candle(
                timestamp=_ts(i),
                open=open_,
                high=max(open_, close, high),
                low=min(open_, close, low),
                close=close,
                volume=vols[i],
                exchange=ExchangeId.BINANCE,
                symbol="BTC/USDT",
                market_type=MarketType.SPOT,
                is_closed=True,
            )
        )
    if forming_last and out:
        out[-1] = out[-1].model_copy(update={"is_closed": False})
    return out


# Deterministic ascending / oscillating series
CLOSE_SERIES = [
    100.0,
    101.0,
    102.0,
    101.5,
    103.0,
    104.0,
    103.5,
    105.0,
    106.0,
    105.5,
    107.0,
    108.0,
    107.5,
    109.0,
    110.0,
    109.5,
    111.0,
    112.0,
    111.5,
    113.0,
    114.0,
    113.5,
    115.0,
    116.0,
    115.5,
    117.0,
    118.0,
    117.5,
    119.0,
    120.0,
    119.5,
    121.0,
    122.0,
    121.5,
    123.0,
    124.0,
    123.5,
    125.0,
    126.0,
    125.5,
]


def test_sma_known_window() -> None:
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=float)
    result = moving_averages.sma(values, 3)
    assert np.isnan(result[0]) and np.isnan(result[1])
    assert result[2] == pytest.approx(2.0)
    assert result[3] == pytest.approx(3.0)
    assert result[4] == pytest.approx(4.0)


def test_ema_seed_and_recursion() -> None:
    values = np.array([10.0, 11.0, 12.0, 13.0, 14.0], dtype=float)
    result = moving_averages.ema(values, 3)
    assert np.isnan(result[0]) and np.isnan(result[1])
    assert result[2] == pytest.approx(11.0)  # SMA seed
    alpha = 2.0 / 4.0
    expected = alpha * 13.0 + (1 - alpha) * 11.0
    assert result[3] == pytest.approx(expected)
    expected2 = alpha * 14.0 + (1 - alpha) * expected
    assert result[4] == pytest.approx(expected2)


def test_rsi_all_gains_is_100() -> None:
    closes = np.arange(100.0, 120.0, dtype=float)
    rsi = momentum.rsi(closes, 14)
    assert np.isnan(rsi[13])
    assert rsi[14] == pytest.approx(100.0)
    assert rsi[-1] == pytest.approx(100.0)


def test_rsi_all_losses_is_0() -> None:
    closes = np.arange(120.0, 100.0, -1.0, dtype=float)
    rsi = momentum.rsi(closes, 14)
    assert rsi[14] == pytest.approx(0.0)


def test_rsi_flat_is_50() -> None:
    closes = np.full(30, 50.0, dtype=float)
    rsi = momentum.rsi(closes, 14)
    assert rsi[14] == pytest.approx(50.0)


def test_macd_shapes_and_warmup() -> None:
    closes = np.asarray(CLOSE_SERIES, dtype=float)
    macd_line, signal, hist = momentum.macd(closes, 12, 26, 9)
    assert len(macd_line) == len(closes)
    # Slow EMA seeds at index 25
    assert np.isnan(macd_line[24])
    assert np.isfinite(macd_line[25])
    # Signal needs 9 finite MACD points → first signal at 25+8=33
    assert np.isnan(signal[32])
    assert np.isfinite(signal[33])
    assert hist[33] == pytest.approx(macd_line[33] - signal[33])


def test_atr_and_bollinger() -> None:
    closes = np.asarray(CLOSE_SERIES, dtype=float)
    highs = closes + 2.0
    lows = closes - 2.0
    atr = volatility.atr(highs, lows, closes, 14)
    assert np.isnan(atr[12])
    assert np.isfinite(atr[13])
    mid, upper, lower = volatility.bollinger_bands(closes, 20, 2.0)
    assert np.isnan(mid[18])
    assert np.isfinite(mid[19])
    assert upper[19] > mid[19] > lower[19]


def test_obv_and_relative_volume() -> None:
    closes = np.array([10.0, 11.0, 10.5, 10.5, 12.0], dtype=float)
    vols = np.array([100.0, 50.0, 40.0, 30.0, 80.0], dtype=float)
    obv = volume.obv(closes, vols)
    assert obv[0] == 0.0
    assert obv[1] == 50.0
    assert obv[2] == 10.0
    assert obv[3] == 10.0  # flat close
    assert obv[4] == 90.0

    rvol = volume.relative_volume(vols, 3)
    assert np.isnan(rvol[1])
    assert rvol[2] == pytest.approx(40.0 / ((100 + 50 + 40) / 3))


def test_insufficient_history_status() -> None:
    candles = make_candles(CLOSE_SERIES[:10])
    bundle = calculate_indicators(candles, indicators=[IndicatorId.EMA_50, IndicatorId.RSI_14])
    assert bundle.latest["ema_50"].status == IndicatorStatus.WARMING_UP
    assert bundle.latest["ema_50"].value is None
    assert bundle.latest["rsi_14"].status == IndicatorStatus.WARMING_UP


def test_ready_after_warmup() -> None:
    # Need enough bars for EMA20 + RSI14
    closes = [100.0 + i * 0.5 for i in range(40)]
    candles = make_candles(closes)
    bundle = calculate_indicators(candles, indicators=[IndicatorId.EMA_20, IndicatorId.SMA_20, IndicatorId.RSI_14])
    assert bundle.latest["ema_20"].status == IndicatorStatus.READY
    assert bundle.latest["ema_20"].value is not None
    assert bundle.latest["sma_20"].status == IndicatorStatus.READY
    assert bundle.latest["rsi_14"].status == IndicatorStatus.READY


def test_chronological_ordering_and_no_lookahead() -> None:
    closes = [100.0 + i for i in range(30)]
    candles = make_candles(closes)
    # Reverse input order — calculator must sort ascending
    shuffled = list(reversed(candles))
    bundle = calculate_indicators(
        shuffled,
        indicators=[IndicatorId.SMA_20],
        include_series=True,
    )
    points = bundle.series["sma_20"].points
    assert points
    timestamps = [p.timestamp for p in points]
    assert timestamps == sorted(timestamps)

    # At index 19, SMA uses only first 20 closes — not future bars
    frame = candles_to_frame(candles)
    sma = moving_averages.sma(np.asarray(frame.close, dtype=float), 20)
    expected = float(np.mean(closes[:20]))
    assert sma[19] == pytest.approx(expected)


def test_forming_vs_closed_candles() -> None:
    closes = [100.0 + i for i in range(25)]
    closed_only = make_candles(closes, forming_last=True)
    without = calculate_indicators(
        closed_only,
        indicators=[IndicatorId.SMA_20],
        include_forming=False,
    )
    with_forming = calculate_indicators(
        closed_only,
        indicators=[IndicatorId.SMA_20],
        include_forming=True,
    )
    # Closed-only uses 24 bars; forming includes 25th unstable close
    assert without.closed_candles_used == 24
    assert with_forming.forming_included is True
    assert with_forming.latest["sma_20"].is_forming is True
    assert without.latest["sma_20"].is_forming is False
    # Values differ because last close participates only when forming included
    assert without.latest["sma_20"].value != with_forming.latest["sma_20"].value


def test_missing_values_stay_none_not_fabricated() -> None:
    candles = make_candles([100.0, 101.0, 102.0])
    bundle = calculate_indicators(candles, indicators=[IndicatorId.EMA_200, IndicatorId.BOLLINGER])
    assert bundle.latest["ema_200"].value is None
    assert bundle.latest["ema_200"].status != IndicatorStatus.READY
    assert bundle.latest["bollinger"].fields.get("upper") is None


def test_invalid_ohlcv_rejected_by_candle_model() -> None:
    with pytest.raises(ValueError):
        Candle(
            timestamp=_ts(0),
            open=10,
            high=9,
            low=8,
            close=9.5,
            volume=1,
            exchange=ExchangeId.BINANCE,
            symbol="BTC/USDT",
            market_type=MarketType.SPOT,
        )


def test_macd_composite_fields() -> None:
    closes = [100.0 + (i % 7) * 0.3 + i * 0.1 for i in range(80)]
    candles = make_candles(closes)
    bundle = calculate_indicators(candles, indicators=[IndicatorId.MACD, IndicatorId.STOCH_RSI])
    macd = bundle.latest["macd"]
    assert macd.status == IndicatorStatus.READY
    assert macd.value is None
    assert macd.fields["macd"] is not None
    assert macd.fields["signal"] is not None
    assert macd.fields["histogram"] is not None
    stoch = bundle.latest["stoch_rsi"]
    assert stoch.status == IndicatorStatus.READY
    assert "k" in stoch.fields and "d" in stoch.fields


def test_volume_indicators_bundle() -> None:
    closes = [100.0 + i * 0.2 for i in range(40)]
    vols = [1000.0 + (i % 10) * 50 for i in range(40)]
    candles = make_candles(closes, volumes=vols)
    bundle = calculate_indicators(
        candles,
        indicators=[IndicatorId.VOLUME_SMA_20, IndicatorId.OBV, IndicatorId.RELATIVE_VOLUME],
    )
    assert bundle.latest["volume_sma_20"].status == IndicatorStatus.READY
    assert bundle.latest["obv"].status == IndicatorStatus.READY
    assert bundle.latest["relative_volume"].status == IndicatorStatus.READY
    assert bundle.latest["relative_volume"].value is not None
