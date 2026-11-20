"""Volume indicators: Volume SMA, OBV, Relative Volume."""

from __future__ import annotations

import numpy as np

from app.analysis.indicators.moving_averages import sma


def volume_sma(volume: np.ndarray, period: int = 20) -> np.ndarray:
    """Simple moving average of volume."""
    return sma(volume.astype(float), period)


def obv(closes: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """
    On-Balance Volume.

    Cumulative: add volume when close rises, subtract when close falls,
    unchanged when close is flat. Starts at 0 on the first bar.
    """
    n = len(closes)
    out = np.full(n, np.nan, dtype=float)
    if n == 0:
        return out
    out[0] = 0.0
    running = 0.0
    for i in range(1, n):
        if closes[i] > closes[i - 1]:
            running += float(volume[i])
        elif closes[i] < closes[i - 1]:
            running -= float(volume[i])
        out[i] = running
    return out


def relative_volume(volume: np.ndarray, period: int = 20) -> np.ndarray:
    """
    Relative volume = current volume / SMA(volume, period).

    NaN until SMA is available or when SMA is 0.
    """
    avg = volume_sma(volume, period)
    out = np.full(len(volume), np.nan, dtype=float)
    for i, (v, a) in enumerate(zip(volume, avg, strict=False)):
        if not np.isfinite(a) or a == 0:
            continue
        out[i] = float(v) / float(a)
    return out
