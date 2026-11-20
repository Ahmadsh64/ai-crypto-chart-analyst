"""Momentum indicators: RSI, MACD, Stochastic RSI."""

from __future__ import annotations

import numpy as np

from app.analysis.indicators.moving_averages import ema


def rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """
    Relative Strength Index using Wilder smoothing.

    Needs at least period+1 closes. Output is aligned to close timestamps;
    values before warm-up are NaN. Uses only past deltas (no look-ahead).
    """
    n = len(closes)
    out = np.full(n, np.nan, dtype=float)
    if n < period + 1 or period <= 0:
        return out

    deltas = np.diff(closes.astype(float))
    gains = np.clip(deltas, 0.0, None)
    losses = np.clip(-deltas, 0.0, None)

    avg_gain = float(np.sum(gains[:period]) / period)
    avg_loss = float(np.sum(losses[:period]) / period)

    def _rsi_from_avgs(g: float, l: float) -> float:
        if l == 0.0 and g == 0.0:
            return 50.0
        if l == 0.0:
            return 100.0
        rs = g / l
        return 100.0 - (100.0 / (1.0 + rs))

    # First RSI value appears at close index `period` (after `period` changes).
    out[period] = _rsi_from_avgs(avg_gain, avg_loss)

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + float(gains[i])) / period
        avg_loss = (avg_loss * (period - 1) + float(losses[i])) / period
        out[i + 1] = _rsi_from_avgs(avg_gain, avg_loss)
    return out


def macd(
    closes: np.ndarray,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (macd_line, signal, histogram). NaN until warm-up completes."""
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    macd_line = fast_ema - slow_ema

    n = len(closes)
    signal = np.full(n, np.nan, dtype=float)
    valid_idx = np.where(np.isfinite(macd_line))[0]
    if len(valid_idx) >= signal_period:
        start = int(valid_idx[0])
        series = macd_line[start:]
        # series starts with finite values from EMA seed point onward.
        sig_part = ema(series, signal_period)
        signal[start:] = sig_part

    histogram = macd_line - signal
    return macd_line, signal, histogram


def stochastic_rsi(
    closes: np.ndarray,
    rsi_period: int = 14,
    stoch_period: int = 14,
    k_smooth: int = 3,
    d_smooth: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Stochastic RSI (%K, %D).

    %K = SMA of raw stoch(RSI) over k_smooth
    %D = SMA of %K over d_smooth
    """
    rsi_vals = rsi(closes, rsi_period)
    n = len(closes)
    raw = np.full(n, np.nan, dtype=float)

    for i in range(n):
        if not np.isfinite(rsi_vals[i]):
            continue
        start = i - stoch_period + 1
        if start < 0:
            continue
        window = rsi_vals[start : i + 1]
        if np.any(~np.isfinite(window)):
            continue
        lowest = float(np.min(window))
        highest = float(np.max(window))
        if highest == lowest:
            raw[i] = 0.0
        else:
            raw[i] = (float(rsi_vals[i]) - lowest) / (highest - lowest) * 100.0

    def _finite_sma(source: np.ndarray, period: int) -> np.ndarray:
        out = np.full(n, np.nan, dtype=float)
        for i in range(n):
            start = i - period + 1
            if start < 0:
                continue
            window = source[start : i + 1]
            if np.any(~np.isfinite(window)):
                continue
            out[i] = float(np.mean(window))
        return out

    k = _finite_sma(raw, k_smooth)
    d = _finite_sma(k, d_smooth)
    return k, d
