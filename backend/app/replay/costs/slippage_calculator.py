"""Deterministic adverse slippage (Phase 5.2.3).

Does not change Phase 5.2.2 trigger prices. Adjusts cost-layer execution price only.
"""

from __future__ import annotations

from decimal import Decimal

from app.replay.costs.config import ExecutionCostConfig
from app.replay.costs.enums import ExecutionRole, SlippagePolicy
from app.replay.simulation.enums import TradeDirection


def _adverse_sign(direction: TradeDirection, role: ExecutionRole) -> Decimal:
    """+1 means raise price; -1 means lower price (adverse to the trader)."""
    if direction == "LONG":
        return Decimal("1") if role == "entry" else Decimal("-1")
    # SHORT
    return Decimal("-1") if role == "entry" else Decimal("1")


def apply_slippage(
    reference_price: Decimal,
    *,
    direction: TradeDirection,
    role: ExecutionRole,
    config: ExecutionCostConfig,
) -> tuple[Decimal, Decimal, list[str]]:
    """
    Returns (execution_price_after_slippage, slippage_cost_absolute, warnings).

    slippage_cost_absolute is always >= 0 (adverse cost magnitude in price * later qty).
    """
    warnings: list[str] = []
    policy: SlippagePolicy = config.slippage_policy
    if policy == "none":
        return reference_price, Decimal("0"), warnings

    if reference_price <= 0:
        warnings.append("Missing/invalid reference price for slippage; skipped.")
        return reference_price, Decimal("0"), warnings

    sign = _adverse_sign(direction, role)
    if policy == "fixed_bps":
        delta = reference_price * (config.slippage_bps / Decimal("10000"))
    elif policy == "percentage":
        delta = reference_price * config.slippage_percentage
    elif policy == "conservative_ohlcv":
        # Slightly larger adverse bump than fixed_bps using configured bps as floor.
        base = config.slippage_bps if config.slippage_bps > 0 else Decimal("2")
        delta = reference_price * (base / Decimal("10000"))
        warnings.append(
            "conservative_ohlcv slippage is a deterministic assumption — "
            "not derived from order-book depth."
        )
    else:
        warnings.append(f"Unknown slippage policy {policy!r}; none applied.")
        return reference_price, Decimal("0"), warnings

    exec_price = reference_price + (sign * delta)
    if exec_price <= 0:
        warnings.append("Slippage would produce non-positive price; clamped.")
        exec_price = reference_price
        delta = Decimal("0")
    return exec_price, delta, warnings


def slippage_cost_for_qty(slippage_price_delta: Decimal, quantity: Decimal) -> Decimal:
    return (slippage_price_delta * quantity).quantize(Decimal("0.00000001"))
