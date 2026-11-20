"""Volatility indicators: ATR and Bollinger Bands."""

from __future__ import annotations

import numpy as np

from app.analysis.indicators.moving_averages import sma


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """True range; index 0 uses high-low only (no prior close)."""
    n = len(close)
    tr = np.full(n, np.nan, dtype=float)
    if n == 0:
        return tr
    tr[0] = float(high[0] - low[0])
    for i in range(1, n):
        hl = float(high[i] - low[i])
        hc = abs(float(high[i] - close[i - 1]))
        lc = abs(float(low[i] - close[i - 1]))
        tr[i] = max(hl, hc, lc)
    return tr


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """Average True Range (Wilder)."""
    n = len(close)
    out = np.full(n, np.nan, dtype=float)
    if n < period or period <= 0:
        return out

    tr = true_range(high, low, close)
    seed = float(np.mean(tr[:period]))
    out[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = (prev * (period - 1) + float(tr[i])) / period
        out[i] = prev
    return out


def bollinger_bands(
    closes: np.ndarray,
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Bollinger Bands: middle (SMA), upper, lower.

    Population uses sample std of the same window (ddof=0) for deterministic
    trading-platform style bands.
    """
    n = len(closes)
    mid = sma(closes, period)
    upper = np.full(n, np.nan, dtype=float)
    lower = np.full(n, np.nan, dtype=float)
    for i in range(period - 1, n):
        window = closes[i - period + 1 : i + 1].astype(float)
        sigma = float(np.std(window, ddof=0))
        m = float(mid[i])
        upper[i] = m + std_dev * sigma
        lower[i] = m - std_dev * sigma
    return mid, upper, lower
