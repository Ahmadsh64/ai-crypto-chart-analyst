"""Trade joining for the backtest report (Phase 5.2.6).

Joins analytics classification with the underlying ``SimulatedTrade`` and the
cost ledger to expose per-trade entry/exit prices, SL/TP, fees, and R multiple.
No metric formulas are redefined here — fees/slippage/spread come from
``TradeCostSummary``; R multiple reuses ``risk_metrics.planned_risk_amount``.
"""

from __future__ import annotations

from decimal import Decimal

from app.replay.analytics.risk_metrics import planned_risk_amount
from app.replay.analytics.trade_filter import ClassifiedTrade
from app.replay.costs.engine import CostEngine
from app.replay.reporting.models import ReportOpenTrade, ReportTradeDetail
from app.replay.simulation.models import SimulatedTrade

_QUANT = Decimal("0.00000001")


def _d(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


def _tp_levels(trade: SimulatedTrade) -> list[Decimal]:
    out: list[Decimal] = []
    for v in trade.take_profit_levels or []:
        dv = _d(v)
        if dv is not None:
            out.append(dv)
    return out


def _average_exit_price(cost_engine: CostEngine, trade_id: str) -> Decimal | None:
    """Quantity-weighted VWAP across exit-role ledger entries for this trade."""
    exits = [
        e
        for e in cost_engine.ledger.for_trade(trade_id)
        if e.execution_role == "exit"
    ]
    if not exits:
        return None
    total_qty = sum((e.executed_quantity for e in exits), Decimal("0"))
    if total_qty <= 0:
        return None
    notional = sum(
        (e.executed_quantity * e.execution_price for e in exits), Decimal("0")
    )
    return (notional / total_qty).quantize(_QUANT)


def _r_multiple(item: ClassifiedTrade) -> Decimal | None:
    if item.cost is None:
        return None
    risk = planned_risk_amount(item)
    if risk is None or risk <= 0:
        return None
    try:
        return (item.cost.net_realized_pnl / risk).quantize(_QUANT)
    except Exception:  # noqa: BLE001
        return None


def build_completed_trade_detail(
    item: ClassifiedTrade,
    cost_engine: CostEngine,
) -> ReportTradeDetail:
    t = item.trade
    cost = item.cost
    avg_exit = _average_exit_price(cost_engine, t.trade_id)

    return ReportTradeDetail(
        trade_id=t.trade_id,
        symbol=t.symbol,
        direction=t.direction,
        lifecycle_status=t.lifecycle_status,
        analytics_class=item.analytics_class,
        exit_type=item.exit_type,
        included_in_completed_stats=item.is_completed,
        entry_timestamp=t.entry_timestamp,
        exit_timestamp=t.exit_timestamp,
        entry_price=_d(t.entry_price),
        average_exit_price=avg_exit,
        original_quantity=_d(t.original_quantity),
        executed_quantity=_d(t.executed_quantity),
        remaining_quantity=_d(t.remaining_quantity),
        initial_stop_loss=_d(t.initial_stop_loss),
        current_stop_loss=_d(t.current_stop_loss),
        take_profit_levels=_tp_levels(t),
        gross_realized_pnl=cost.total_gross_realized_pnl if cost else None,
        net_realized_pnl=cost.net_realized_pnl if cost else None,
        fees=cost.total_fees if cost else None,
        slippage=cost.total_slippage if cost else None,
        spread_cost=cost.total_spread_cost if cost else None,
        r_multiple=_r_multiple(item),
    )


def build_open_trade(item: ClassifiedTrade) -> ReportOpenTrade:
    t = item.trade
    return ReportOpenTrade(
        trade_id=t.trade_id,
        symbol=t.symbol,
        direction=t.direction,
        lifecycle_status=t.lifecycle_status,
        analytics_class=item.analytics_class,
        entry_timestamp=t.entry_timestamp,
        entry_price=_d(t.entry_price),
        original_quantity=_d(t.original_quantity),
        remaining_quantity=_d(t.remaining_quantity),
        executed_quantity=_d(t.executed_quantity),
        initial_stop_loss=_d(t.initial_stop_loss),
        current_stop_loss=_d(t.current_stop_loss),
        take_profit_levels=_tp_levels(t),
    )
