"""Gross / net P&L helpers (Phase 5.2.3)."""

from __future__ import annotations

from decimal import Decimal

from app.replay.simulation.enums import TradeDirection


def gross_pnl(
    *,
    direction: TradeDirection,
    entry_price: Decimal,
    exit_price: Decimal,
    quantity: Decimal,
    multiplier: Decimal = Decimal("1"),
) -> Decimal:
    if direction == "LONG":
        raw = (exit_price - entry_price) * quantity * multiplier
    else:
        raw = (entry_price - exit_price) * quantity * multiplier
    return raw.quantize(Decimal("0.00000001"))


def net_pnl(
    *,
    gross: Decimal,
    entry_fee_allocated: Decimal,
    exit_fee: Decimal,
    slippage_cost: Decimal,
    spread_cost: Decimal,
) -> Decimal:
    return (
        gross - entry_fee_allocated - exit_fee - slippage_cost - spread_cost
    ).quantize(Decimal("0.00000001"))


def allocate_entry_fee(
    total_entry_fee: Decimal,
    *,
    exit_qty: Decimal,
    original_qty: Decimal,
) -> Decimal:
    if original_qty <= 0:
        return Decimal("0")
    share = (total_entry_fee * exit_qty / original_qty).quantize(Decimal("0.00000001"))
    return share
