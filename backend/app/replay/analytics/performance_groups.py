"""Grouped performance analytics (Phase 5.2.4)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from app.replay.analytics.config import AnalyticsConfig
from app.replay.analytics.metrics_calculator import (
    available,
    compute_profit_factor,
    unavailable,
)
from app.replay.analytics.models import GroupPerformanceRow, PerformanceGroups
from app.replay.analytics.risk_metrics import planned_risk_amount
from app.replay.analytics.trade_filter import ClassifiedTrade
from app.replay.timeline import ensure_utc

ZERO = Decimal("0")


def _period_key(ts: datetime, period: str) -> str:
    ts = ensure_utc(ts)
    if period == "weekly":
        iso = ts.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    if period == "monthly":
        return f"{ts.year}-{ts.month:02d}"
    return ts.strftime("%Y-%m-%d")


def _group_rows(buckets: dict[str, list[ClassifiedTrade]]) -> list[GroupPerformanceRow]:
    rows: list[GroupPerformanceRow] = []
    for key in sorted(buckets.keys()):
        items = buckets[key]
        completed = [i for i in items if i.is_completed and i.cost is not None]
        wins = sum(
            1 for i in completed if i.cost is not None and i.cost.net_realized_pnl > 0
        )
        n = len(completed)
        net = sum((i.cost.net_realized_pnl for i in completed if i.cost), ZERO)
        gp = sum(
            (i.cost.net_realized_pnl for i in completed if i.cost and i.cost.net_realized_pnl > 0),
            ZERO,
        )
        gl = sum(
            (i.cost.net_realized_pnl for i in completed if i.cost and i.cost.net_realized_pnl < 0),
            ZERO,
        )
        r_vals: list[Decimal] = []
        for i in completed:
            risk = planned_risk_amount(i)
            if risk and i.cost:
                r_vals.append(i.cost.net_realized_pnl / risk)

        rows.append(
            GroupPerformanceRow(
                key=key,
                completed_trades=n,
                win_rate=(
                    available(Decimal(wins) / Decimal(n) * Decimal("100"))
                    if n
                    else unavailable("no_completed_trades")
                ),
                net_pnl=net.quantize(Decimal("0.00000001")),
                profit_factor=compute_profit_factor(gp, gl),
                average_net_trade=(
                    available(net / Decimal(n)) if n else unavailable("no_completed_trades")
                ),
                average_r_multiple=(
                    available(sum(r_vals) / Decimal(len(r_vals)))
                    if r_vals
                    else unavailable("missing_risk_metadata")
                ),
            )
        )
    return rows


def build_groups(
    items: list[ClassifiedTrade],
    config: AnalyticsConfig,
) -> PerformanceGroups:
    warnings: list[str] = []
    groups = PerformanceGroups()

    completed = [i for i in items if i.is_completed and i.cost is not None]

    if config.group_by_symbol:
        buckets: dict[str, list[ClassifiedTrade]] = defaultdict(list)
        for i in completed:
            buckets[i.trade.symbol].append(i)
        groups.by_symbol = _group_rows(buckets)

    if config.group_by_direction:
        buckets = defaultdict(list)
        for i in completed:
            buckets[i.trade.direction].append(i)
        groups.by_direction = _group_rows(buckets)

    if config.group_by_exit_type:
        buckets = defaultdict(list)
        for i in completed:
            buckets[i.exit_type].append(i)
        groups.by_exit_type = _group_rows(buckets)

    if config.group_by_period:
        buckets = defaultdict(list)
        for i in completed:
            ts = i.trade.exit_timestamp or i.trade.decision_timestamp
            buckets[_period_key(ts, config.time_group_period)].append(i)
        groups.by_period = _group_rows(buckets)

    if config.group_by_timeframe:
        # SimulatedTrade has no per-trade timeframe field — do not invent.
        groups.timeframe_unavailable_reason = (
            "SimulatedTrade does not store a signal timeframe; "
            "timeframe grouping is unavailable."
        )
        groups.by_timeframe = []
        warnings.append(groups.timeframe_unavailable_reason)

    groups.warnings = warnings
    return groups


def reconcile_group_net(
    groups: list[GroupPerformanceRow],
    overall_net: Decimal,
    *,
    tol: Decimal = Decimal("0.0001"),
) -> bool:
    total = sum((g.net_pnl for g in groups), ZERO)
    return abs(total - overall_net) <= tol
