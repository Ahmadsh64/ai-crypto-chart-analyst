"""Analytics reconciliation helpers (Phase 5.2.4)."""

from __future__ import annotations

from decimal import Decimal

from app.replay.analytics.models import (
    DrawdownSummary,
    EquityCurve,
    PerformanceGroups,
    PerformanceSummary,
)

ZERO = Decimal("0")
TOL = Decimal("0.0001")


def reconcile_summary(summary: PerformanceSummary) -> list[str]:
    warns: list[str] = []
    stats = summary.trade_stats
    if (
        stats.winning_trades + stats.losing_trades + stats.break_even_trades
        != stats.completed_trades
    ):
        warns.append("Win+Loss+BE does not equal completed trades.")

    p = summary.profitability
    expected_costs = p.total_trading_fees + p.total_slippage + p.total_spread_costs
    if abs(expected_costs - p.total_execution_costs) > TOL:
        warns.append("Execution costs do not equal fees+slippage+spread.")

    # Gross − costs ≈ net (within tolerance; cost engine may allocate entry slip)
    approx = p.total_gross_realized_pnl - p.total_execution_costs
    if abs(approx - p.total_net_realized_pnl) > Decimal("0.01"):
        warns.append(
            "Gross−costs vs net divergence exceeds 0.01 "
            "(may include entry slip/spread allocation)."
        )
    return warns


def reconcile_equity(
    curve: EquityCurve,
    *,
    initial_equity: Decimal | None,
    cumulative_net: Decimal,
) -> list[str]:
    warns: list[str] = []
    if not curve.points:
        return warns
    # Chronological
    prev = curve.points[0].timestamp
    for p in curve.points[1:]:
        if p.timestamp < prev:
            warns.append("Equity curve timestamps are not chronological.")
            break
        prev = p.timestamp

    if abs(curve.cumulative_net_pnl - cumulative_net) > TOL:
        warns.append("Equity cumulative net does not match profitability net.")

    if initial_equity is not None and curve.ending_equity is not None:
        expected = initial_equity + cumulative_net
        if abs(curve.ending_equity - expected) > TOL:
            warns.append("Ending equity != initial + cumulative net.")
    return warns


def reconcile_drawdown(dd: DrawdownSummary) -> list[str]:
    warns: list[str] = []
    if not dd.available:
        return warns
    for p in dd.series:
        if p.drawdown < 0:
            warns.append("Negative drawdown observed.")
            break
    if dd.series:
        observed = max((p.drawdown for p in dd.series), default=ZERO)
        if abs(observed - dd.max_drawdown) > TOL:
            warns.append("max_drawdown != max observed series drawdown.")
    return warns


def reconcile_groups(
    groups: PerformanceGroups,
    overall_net: Decimal,
) -> list[str]:
    warns: list[str] = []
    for name, rows in (
        ("symbol", groups.by_symbol),
        ("direction", groups.by_direction),
        ("exit_type", groups.by_exit_type),
        ("period", groups.by_period),
    ):
        if not rows:
            continue
        total = sum((r.net_pnl for r in rows), ZERO)
        if abs(total - overall_net) > TOL:
            warns.append(f"Group by {name} net does not reconcile to overall net.")
    return warns
