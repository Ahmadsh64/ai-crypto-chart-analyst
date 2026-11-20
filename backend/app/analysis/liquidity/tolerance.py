"""Deterministic tolerance and penetration helpers."""

from __future__ import annotations

import math

from app.analysis.liquidity.config import LiquidityConfig


def is_finite_positive(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0


def cluster_tolerance(
    price_a: float,
    price_b: float,
    atr_at_later: float | None,
    cfg: LiquidityConfig,
) -> tuple[float, bool]:
    """
    Return (tolerance, atr_available) for a price pair / diameter budget.

    ATR path: atr_tolerance_mult × ATR at later confirmation bar.
    Fallback: fallback_tolerance_pct × mid-price.
    """
    if is_finite_positive(atr_at_later):
        return float(cfg.atr_tolerance_mult * atr_at_later), True
    mid = (float(price_a) + float(price_b)) / 2.0
    return float(cfg.fallback_tolerance_pct * mid), False


def diameter_tolerance(
    prices: list[float],
    atr_at_latest: float | None,
    cfg: LiquidityConfig,
) -> tuple[float, bool]:
    """
    Diameter budget for a candidate cluster: max(prices)-min(prices) must be ≤ T.

    T uses ATR at the latest confirmation among members when available;
    otherwise fallback % of the mid of min/max prices.
    """
    if not prices:
        raise ValueError("diameter_tolerance requires prices")
    lo = min(float(p) for p in prices)
    hi = max(float(p) for p in prices)
    return cluster_tolerance(lo, hi, atr_at_latest, cfg)


def penetration_distance(
    level: float,
    atr_value: float | None,
    cfg: LiquidityConfig,
) -> float:
    fallback = float(cfg.min_penetration_fallback_pct) * float(level)
    if is_finite_positive(atr_value):
        return max(float(cfg.min_penetration_atr_mult) * float(atr_value), fallback)
    return fallback


def median_price(prices: list[float]) -> float:
    ordered = sorted(float(p) for p in prices)
    n = len(ordered)
    if n == 0:
        raise ValueError("median_price requires at least one price")
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0
