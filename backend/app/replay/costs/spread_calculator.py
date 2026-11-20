"""Spread cost modeling (Phase 5.2.3).

Historical bid/ask is not available in replay OHLCV. Any non-none policy is
synthetic unless explicitly documented otherwise.
"""

from __future__ import annotations

from decimal import Decimal

from app.replay.costs.config import ExecutionCostConfig
from app.replay.costs.enums import ExecutionRole, SpreadPolicy
from app.replay.simulation.enums import TradeDirection


def _adverse_sign(direction: TradeDirection, role: ExecutionRole) -> Decimal:
    if direction == "LONG":
        return Decimal("1") if role == "entry" else Decimal("-1")
    return Decimal("-1") if role == "entry" else Decimal("1")


def apply_half_spread(
    price: Decimal,
    *,
    direction: TradeDirection,
    role: ExecutionRole,
    config: ExecutionCostConfig,
) -> tuple[Decimal, Decimal, list[str], list[str]]:
    """
    Apply half-spread adversely.

    Returns (adjusted_price, half_spread_price_delta, assumptions, warnings).
    """
    assumptions: list[str] = []
    warnings: list[str] = []
    policy: SpreadPolicy = config.spread_policy

    if policy == "none":
        return price, Decimal("0"), assumptions, warnings

    if price <= 0:
        warnings.append("Invalid price for spread; skipped.")
        return price, Decimal("0"), assumptions, warnings

    if policy in {"fixed_bps", "percentage", "synthetic_assumption"}:
        assumptions.append(
            "Spread is a SYNTHETIC ASSUMPTION — not observed historical bid/ask."
        )
    else:
        warnings.append(f"Unknown spread policy {policy!r}; none applied.")
        return price, Decimal("0"), assumptions, warnings

    if policy == "fixed_bps" or policy == "synthetic_assumption":
        full = price * (config.spread_bps / Decimal("10000"))
    else:  # percentage
        full = price * config.spread_percentage

    half = full / Decimal("2")
    sign = _adverse_sign(direction, role)
    adjusted = price + (sign * half)
    if adjusted <= 0:
        warnings.append("Spread adjustment non-positive; skipped.")
        return price, Decimal("0"), assumptions, warnings
    return adjusted, half, assumptions, warnings


def spread_cost_for_qty(half_spread_delta: Decimal, quantity: Decimal) -> Decimal:
    return (half_spread_delta * quantity).quantize(Decimal("0.00000001"))
