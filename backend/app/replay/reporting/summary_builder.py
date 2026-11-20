"""Report summary assembler (Phase 5.2.6).

Translates the existing ``PerformanceSummary`` into a flat report view that
preserves ``MetricValue`` availability semantics. Does not reinvent any metric.
"""

from __future__ import annotations

from app.replay.analytics.models import PerformanceSummary
from app.replay.reporting.models import ReportKeyMetric, ReportSummary


def build_report_summary(summary: PerformanceSummary) -> ReportSummary:
    ts = summary.trade_stats
    prof = summary.profitability
    rr = summary.risk_reward
    ret = summary.returns
    dd = summary.drawdown

    out = ReportSummary(
        completed_trade_count=ts.completed_trades,
        total_simulated_trades=ts.total_simulated_trades,
        winning_trades=ts.winning_trades,
        losing_trades=ts.losing_trades,
        break_even_trades=ts.break_even_trades,
        partially_closed_trades=ts.partially_closed_trades,
        open_trades=ts.open_trades,
        excluded_open_trades=summary.excluded_open_trades,
        excluded_partial_trades=summary.excluded_partial_trades,
        win_rate=ts.win_rate,
        profit_factor=prof.profit_factor,
        average_net_pnl_per_completed=prof.average_net_pnl_per_completed,
        average_r_multiple=rr.average_r_multiple,
        gross_pnl=prof.total_gross_realized_pnl,
        net_pnl=prof.total_net_realized_pnl,
        total_fees=prof.total_trading_fees,
        total_slippage=prof.total_slippage,
        total_spread_cost=prof.total_spread_costs,
        total_execution_costs=prof.total_execution_costs,
        initial_equity=summary.initial_equity,
        ending_equity=ret.ending_equity,
        current_equity=ret.current_equity,
        total_return_pct=ret.total_return_pct,
        max_drawdown=dd.max_drawdown,
        max_drawdown_pct=dd.max_drawdown_pct,
        current_drawdown=dd.current_drawdown,
        recovery_timestamp=dd.recovery_timestamp,
        peak_timestamp=dd.peak_timestamp,
        trough_timestamp=dd.trough_timestamp,
    )

    out.key_metrics = [
        ReportKeyMetric.decimal("net_pnl", "Net P&L", prof.total_net_realized_pnl),
        ReportKeyMetric.decimal("gross_pnl", "Gross P&L", prof.total_gross_realized_pnl),
        ReportKeyMetric.from_metric("win_rate", "Win Rate", ts.win_rate, unit="%"),
        ReportKeyMetric.from_metric(
            "profit_factor", "Profit Factor", prof.profit_factor
        ),
        ReportKeyMetric.from_metric(
            "average_r_multiple", "Average R", rr.average_r_multiple
        ),
        ReportKeyMetric.decimal(
            "max_drawdown", "Max Drawdown", dd.max_drawdown
        ),
        ReportKeyMetric.from_metric(
            "max_drawdown_pct", "Max Drawdown %", dd.max_drawdown_pct, unit="%"
        ),
        ReportKeyMetric.from_metric(
            "ending_equity", "Ending Equity", ret.ending_equity
        ),
        ReportKeyMetric.decimal(
            "total_execution_costs",
            "Total Execution Costs",
            prof.total_execution_costs,
        ),
    ]
    return out
