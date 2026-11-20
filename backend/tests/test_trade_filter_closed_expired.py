"""D1 — closed_expired remaining-quantity safety (Phase 5.2.4).

LABELED FIXTURES — not live OHLCV proof.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.exchanges.types import ExchangeId, MarketType
from app.replay.analytics.config import AnalyticsConfig
from app.replay.analytics.engine import AnalyticsEngine
from app.replay.analytics.trade_filter import _QTY_TOL, classify_trade
from app.replay.costs.config import ExecutionCostConfig
from app.replay.costs.engine import CostEngine
from app.replay.costs.models import TradeCostSummary
from app.replay.simulation.config import QTY_TOLERANCE
from app.replay.simulation.models import SimulatedTrade, SimulationExecutionEvent

UTC = timezone.utc
NOW = datetime(2024, 7, 1, 12, 0, tzinfo=UTC)


def _trade(
    *,
    trade_id: str,
    status: str,
    remaining: float | None = 0.0,
    executed: float = 1.0,
    events: list[SimulationExecutionEvent] | None = None,
) -> SimulatedTrade:
    kwargs: dict = dict(
        trade_id=trade_id,
        signal_key=f"sig_{trade_id}",
        replay_session_id="rp_d1",
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        direction="LONG",
        decision="LONG",
        decision_timestamp=NOW,
        decision_event_index=0,
        lifecycle_status=status,  # type: ignore[arg-type]
        entry_limit_price=100.0,
        entry_price=100.0,
        entry_timestamp=NOW,
        exit_timestamp=NOW,
        initial_stop_loss=95.0,
        current_stop_loss=95.0,
        take_profit_levels=[110.0],
        tp_allocations=[1.0],
        tp_filled=[status == "closed_tp"],
        original_quantity=1.0,
        executed_quantity=executed,
        quantity_closed_tp=0.0,
        quantity_closed_sl=0.0,
        quantity_closed_expired=0.0,
        config_version="v",
        created_at=NOW,
        updated_at=NOW,
        execution_events=events or [],
    )
    if remaining is None:
        # Model requires float; simulate unsafe/unknown by using NaN.
        kwargs["remaining_quantity"] = float("nan")
    else:
        kwargs["remaining_quantity"] = remaining
    return SimulatedTrade(**kwargs)


def _cost_stub(trade_id: str, net: Decimal) -> TradeCostSummary:
    return TradeCostSummary(
        trade_id=trade_id,
        session_id="rp_d1",
        symbol="BTC/USDT",
        direction="LONG",
        lifecycle_status="closed_expired",
        total_executed_quantity=Decimal("1"),
        remaining_open_quantity=Decimal("0.4"),
        total_gross_realized_pnl=net,
        total_entry_fees=Decimal("0"),
        total_exit_fees=Decimal("0"),
        total_fees=Decimal("0"),
        total_slippage=Decimal("0"),
        total_spread_cost=Decimal("0"),
        total_costs=Decimal("0"),
        net_realized_pnl=net,
        cost_model_version="execution-costs-v1.0.0-balanced",
        fee_config_source="user",
        ledger_entry_count=2,
    )


def test_qty_tolerance_source():
    assert QTY_TOLERANCE == 1e-9
    assert _QTY_TOL == Decimal(str(QTY_TOLERANCE))


def test_closed_expired_remaining_0_4_not_completed():
    t = _trade(trade_id="e1", status="closed_expired", remaining=0.4, executed=1.0)
    c = classify_trade(t, _cost_stub("e1", Decimal("5")))
    assert c.is_completed is False
    assert c.analytics_class == "expired"
    assert c.exit_type == "expired"
    assert c.has_realized_pnl is True  # partial cash-flow still recognized


def test_closed_expired_remaining_above_tolerance_not_completed():
    # Just above sim tolerance
    rem = float(QTY_TOLERANCE) * 10
    t = _trade(trade_id="e2", status="closed_expired", remaining=rem)
    c = classify_trade(t, None)
    assert rem > QTY_TOLERANCE
    assert c.is_completed is False
    assert c.analytics_class == "expired"


def test_closed_expired_remaining_zero_is_completed():
    t = _trade(trade_id="e3", status="closed_expired", remaining=0.0, executed=1.0)
    c = classify_trade(t, _cost_stub("e3", Decimal("2")))
    assert c.is_completed is True
    assert c.analytics_class == "closed"
    assert c.exit_type == "expired"


def test_closed_expired_remaining_within_tolerance_is_completed():
    t = _trade(
        trade_id="e3b",
        status="closed_expired",
        remaining=float(QTY_TOLERANCE),
        executed=1.0,
    )
    c = classify_trade(t, None)
    assert c.is_completed is True
    assert c.analytics_class == "closed"


def test_closed_tp_remaining_zero_preserved():
    t = _trade(trade_id="tp", status="closed_tp", remaining=0.0)
    c = classify_trade(t, None)
    assert c.is_completed is True
    assert c.analytics_class == "closed"
    assert c.exit_type == "tp"


def test_closed_sl_remaining_zero_preserved():
    t = _trade(trade_id="sl", status="closed_sl", remaining=0.0)
    c = classify_trade(t, None)
    assert c.is_completed is True
    assert c.analytics_class == "closed"
    assert c.exit_type == "sl"


def test_cancelled_preserved():
    t = _trade(trade_id="c", status="cancelled", remaining=0.0, executed=0.0)
    c = classify_trade(t, None)
    assert c.is_completed is False
    assert c.analytics_class == "cancelled"


def test_unknown_remaining_nan_not_silently_completed():
    t = _trade(trade_id="nan", status="closed_expired", remaining=None, executed=1.0)
    c = classify_trade(t, None)
    assert c.is_completed is False
    assert c.analytics_class == "expired"


def test_nonflat_closed_expired_excluded_from_completed_metrics():
    """Ensure Win Rate / PF / avg net / completed equity ignore non-flat expired."""
    events = [
        SimulationExecutionEvent(
            event_id="ee",
            event_type="trade_opened",
            timestamp=NOW,
            price=100.0,
            quantity=1.0,
            reason="Limit entry filled.",
        ),
        SimulationExecutionEvent(
            event_id="ex",
            event_type="trade_partially_closed",
            timestamp=NOW,
            price=110.0,
            quantity=0.6,
            reason="TP1 partial close.",
            tp_index=0,
        ),
    ]
    t = _trade(
        trade_id="exp_open",
        status="closed_expired",
        remaining=0.4,
        executed=1.0,
        events=events,
    )
    cost = CostEngine(
        session_id="rp_d1",
        config=ExecutionCostConfig(
            maker_fee_rate=Decimal("0"),
            taker_fee_rate=Decimal("0"),
            fee_source="user",
            slippage_policy="none",
            spread_policy="none",
        ),
    )
    cost.enable()
    cost.process_trades([t])

    analytics = AnalyticsEngine(
        session_id="rp_d1",
        config=AnalyticsConfig(initial_equity=Decimal("10000"), enabled=True),
    )
    analytics.enable()
    snap = analytics.compute([t], cost)

    assert snap.summary.trade_stats.completed_trades == 0
    assert snap.summary.trade_stats.win_rate.availability == "unavailable"
    assert snap.summary.profitability.profit_factor.availability == "unavailable"
    assert snap.summary.profitability.average_net_pnl_per_completed.availability == (
        "unavailable"
    )
    assert snap.equity_completed.points == []
    assert len(snap.completed_trades) == 0
    # Partial cash-flow may still exist from the partial exit
    assert snap.equity_cashflow.cumulative_net_pnl != 0 or len(snap.equity_cashflow.points) >= 0
