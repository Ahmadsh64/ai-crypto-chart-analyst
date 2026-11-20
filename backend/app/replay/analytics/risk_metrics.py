"""R-multiple and win/loss ratio metrics (Phase 5.2.4)."""

from __future__ import annotations

from decimal import Decimal

from app.replay.analytics.metrics_calculator import (
    available,
    median_decimal,
    unavailable,
)
from app.replay.analytics.models import RiskRewardMetrics
from app.replay.analytics.trade_filter import ClassifiedTrade

ZERO = Decimal("0")
_EPS = Decimal("1e-12")


def planned_risk_amount(item: ClassifiedTrade) -> Decimal | None:
    """Original entry-to-SL risk in quote currency. None if metadata invalid."""
    t = item.trade
    entry = t.entry_price
    sl = t.initial_stop_loss
    qty = t.original_quantity or t.executed_quantity
    if entry is None or qty is None or qty <= 0:
        return None
    risk_per_unit = abs(Decimal(str(entry)) - Decimal(str(sl)))
    if risk_per_unit <= _EPS:
        return None
    return (risk_per_unit * Decimal(str(qty))).quantize(Decimal("0.00000001"))


def compute_risk_reward(completed: list[ClassifiedTrade]) -> RiskRewardMetrics:
    mets = RiskRewardMetrics()
    r_values: list[Decimal] = []
    missing = 0
    for item in completed:
        if item.cost is None:
            missing += 1
            continue
        risk = planned_risk_amount(item)
        if risk is None:
            missing += 1
            continue
        r_values.append(
            (item.cost.net_realized_pnl / risk).quantize(Decimal("0.00000001"))
        )

    mets.r_multiple_sample_count = len(r_values)
    mets.missing_risk_metadata_count = missing

    if not r_values:
        mets.average_r_multiple = unavailable("missing_risk_metadata")
        mets.median_r_multiple = unavailable("missing_risk_metadata")
        mets.best_r_multiple = unavailable("missing_risk_metadata")
        mets.worst_r_multiple = unavailable("missing_risk_metadata")
    else:
        mets.average_r_multiple = available(sum(r_values) / Decimal(len(r_values)))
        mets.median_r_multiple = available(median_decimal(r_values))
        mets.best_r_multiple = available(max(r_values))
        mets.worst_r_multiple = available(min(r_values))

    wins = [
        i.cost.net_realized_pnl
        for i in completed
        if i.cost is not None and i.cost.net_realized_pnl > 0
    ]
    losses = [
        abs(i.cost.net_realized_pnl)
        for i in completed
        if i.cost is not None and i.cost.net_realized_pnl < 0
    ]
    if wins and losses:
        avg_w = sum(wins) / Decimal(len(wins))
        avg_l = sum(losses) / Decimal(len(losses))
        if avg_l > 0:
            mets.avg_win_loss_ratio = available(avg_w / avg_l)
        else:
            mets.avg_win_loss_ratio = unavailable("zero_average_loss")
    else:
        mets.avg_win_loss_ratio = unavailable("insufficient_wins_or_losses")

    return mets
