"""Moving average indicators (EMA / SMA). No look-ahead."""

from __future__ import annotations

import math

import numpy as np


def sma(values: np.ndarray, period: int) -> np.ndarray:
    """
    Simple moving average.

    Returns an array of the same length with NaN until `period` samples exist.
    Uses only past and current values at each index i (window [i-period+1, i]).
    """
    n = len(values)
    out = np.full(n, np.nan, dtype=float)
    if period <= 0 or n == 0:
        return out
    # Cumulative sum for O(n) SMA without using future bars.
    csum = np.cumsum(np.insert(values.astype(float), 0, 0.0))
    for i in range(period - 1, n):
        window_sum = csum[i + 1] - csum[i + 1 - period]
        out[i] = window_sum / period
    return out


def ema(values: np.ndarray, period: int) -> np.ndarray:
    """
    Exponential moving average.

    Seeded with SMA of the first `period` values at index period-1, then
    recursively updated. Values before the seed remain NaN.
    """
    n = len(values)
    out = np.full(n, np.nan, dtype=float)
    if period <= 0 or n < period:
        return out

    alpha = 2.0 / (period + 1.0)
    seed = float(np.mean(values[:period]))
    out[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = alpha * float(values[i]) + (1.0 - alpha) * prev
        out[i] = prev
    return out


def last_finite(series: np.ndarray) -> float | None:
    for value in reversed(series):
        if value is not None and not (isinstance(value, float) and math.isnan(value)):
            if np.isfinite(value):
                return float(value)
    return None
