"""Cost-engine validation helpers (Phase 5.2.3)."""

from __future__ import annotations

from decimal import Decimal

from app.replay.costs.models import TradeCostSummary


def reconcile_trade_summary(summary: TradeCostSummary, *, tol: Decimal = Decimal("0.0001")) -> list[str]:
    """Return warning strings if gross/net/costs do not reconcile."""
    warnings: list[str] = []
    expected_costs = (
        summary.total_fees + summary.total_slippage + summary.total_spread_cost
    )
    if abs(expected_costs - summary.total_costs) > tol:
        warnings.append(
            f"Cost total mismatch: fees+slip+spread={expected_costs} vs total_costs={summary.total_costs}"
        )
    expected_net = summary.total_gross_realized_pnl - summary.total_costs
    # Entry fees on remaining open qty are not yet realized as costs against net
    # for open partials — total_costs includes only realized allocated portions.
    if abs(expected_net - summary.net_realized_pnl) > tol:
        warnings.append(
            f"Net P&L mismatch: gross-costs={expected_net} vs net={summary.net_realized_pnl}"
        )
    return warnings


def d(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))
