"""LABELED TEST FIXTURE — not live OHLCV.

Independently reconciles CostEngine P&L for a complete TP1/TP2/TP3 long trade.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.exchanges.types import ExchangeId, MarketType
from app.replay.costs.config import ExecutionCostConfig
from app.replay.costs.engine import CostEngine
from app.replay.costs.slippage_calculator import apply_slippage
from app.replay.costs.spread_calculator import apply_half_spread
from app.replay.simulation.models import SimulatedTrade, SimulationExecutionEvent

UTC = timezone.utc
NOW = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)


def ev(eid, et, price, qty, ts, reason=None, tp=None):
    return SimulationExecutionEvent(
        event_id=eid,
        event_type=et,
        timestamp=ts,
        price=price,
        quantity=qty,
        reason=reason,
        tp_index=tp,
    )


def build_trade() -> SimulatedTrade:
    return SimulatedTrade(
        trade_id="st_qa_fixture",
        signal_key="qa",
        replay_session_id="rp_qa",
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        direction="LONG",
        decision="LONG",
        decision_timestamp=NOW,
        decision_event_index=0,
        lifecycle_status="closed_tp",
        entry_limit_price=100.0,
        entry_price=100.0,
        entry_timestamp=NOW + timedelta(minutes=5),
        initial_stop_loss=95.0,
        current_stop_loss=95.0,
        take_profit_levels=[105.0, 110.0, 115.0],
        tp_allocations=[0.4, 0.3, 0.3],
        tp_filled=[True, True, True],
        original_quantity=1.0,
        remaining_quantity=0.0,
        executed_quantity=1.0,
        quantity_closed_tp=1.0,
        config_version="v",
        created_at=NOW,
        updated_at=NOW,
        execution_events=[
            ev("se1", "trade_opened", 100.0, 1.0, NOW + timedelta(minutes=5), "Limit entry filled."),
            ev(
                "se2",
                "trade_partially_closed",
                105.0,
                0.4,
                NOW + timedelta(minutes=10),
                "TP1 partial close.",
                0,
            ),
            ev(
                "se3",
                "trade_partially_closed",
                110.0,
                0.3,
                NOW + timedelta(minutes=15),
                "TP2 partial close.",
                1,
            ),
            ev(
                "se4",
                "trade_closed",
                115.0,
                0.3,
                NOW + timedelta(minutes=20),
                "TP3 final close.",
                2,
            ),
        ],
    )


def hand_calc(cfg: ExecutionCostConfig) -> dict[str, Decimal]:
    """Directionally adverse LONG adjustments matching engine helpers."""
    from app.replay.costs.slippage_calculator import slippage_cost_for_qty
    from app.replay.costs.spread_calculator import spread_cost_for_qty

    entry_ref = Decimal("100")
    qty = Decimal("1")
    entry_px, entry_slip_delta, _ = apply_slippage(
        entry_ref, direction="LONG", role="entry", config=cfg
    )
    entry_px, entry_spread_delta, _, _ = apply_half_spread(
        entry_px, direction="LONG", role="entry", config=cfg
    )
    entry_fee = (entry_px * qty * cfg.maker_fee_rate).quantize(Decimal("0.00000001"))
    slip = slippage_cost_for_qty(entry_slip_delta, qty)
    spread = spread_cost_for_qty(entry_spread_delta, qty)

    exits = [
        (Decimal("105"), Decimal("0.4")),
        (Decimal("110"), Decimal("0.3")),
        (Decimal("115"), Decimal("0.3")),
    ]
    gross = Decimal("0")
    exit_fees = Decimal("0")
    for ref, q in exits:
        px, s_delta, _ = apply_slippage(ref, direction="LONG", role="exit", config=cfg)
        px, sp_delta, _, _ = apply_half_spread(px, direction="LONG", role="exit", config=cfg)
        fee = (px * q * cfg.maker_fee_rate).quantize(Decimal("0.00000001"))
        leg_gross = ((px - entry_px) * q).quantize(Decimal("0.00000001"))
        gross += leg_gross
        exit_fees += fee
        slip += slippage_cost_for_qty(s_delta, q)
        spread += spread_cost_for_qty(sp_delta, q)

    total_fees = entry_fee + exit_fees
    total_costs = total_fees + slip + spread
    net = gross - total_costs
    return {
        "gross": gross,
        "entry_fees": entry_fee,
        "exit_fees": exit_fees,
        "slip": slip,
        "spread": spread,
        "total_costs": total_costs,
        "net": net,
        "entry_exec_px": entry_px,
    }


def main() -> None:
    cfg = ExecutionCostConfig(
        maker_fee_rate=Decimal("0.001"),
        taker_fee_rate=Decimal("0.001"),
        fee_source="user",
        slippage_policy="fixed_bps",
        slippage_bps=Decimal("1"),
        spread_policy="synthetic_assumption",
        spread_bps=Decimal("2"),
        maker_taker_fallback="assume_taker",
    )
    trade = build_trade()
    eng = CostEngine(session_id="rp_qa", config=cfg)
    eng.enable()
    eng.process_trades([trade])
    ts = eng.trade_summary(trade)
    ss = eng.session_summary([trade])
    entries = eng.ledger.for_trade(trade.trade_id)

    print("FIXTURE_LABEL=test_fixture_not_live_ohlcv")
    print("trade_id", trade.trade_id)
    print("remaining_qty", trade.remaining_quantity)
    print("events", [e.event_type for e in trade.execution_events])
    print("--- engine trade summary ---")
    print("gross", ts.total_gross_realized_pnl)
    print("entry_fees", ts.total_entry_fees)
    print("exit_fees", ts.total_exit_fees)
    print("slip", ts.total_slippage)
    print("spread", ts.total_spread_cost)
    print("total_costs", ts.total_costs)
    print("net", ts.net_realized_pnl)
    print("session_net", ss.net_realized_pnl)
    print("reconcile_ok", abs(ts.total_gross_realized_pnl - ts.total_costs - ts.net_realized_pnl) < Decimal("0.0001"))
    print("session_matches_trade", ss.net_realized_pnl == ts.net_realized_pnl)

    a = [(e.execution_id, str(e.net_realized_pnl)) for e in eng.rebuild_from_trades([trade])]
    b = [(e.execution_id, str(e.net_realized_pnl)) for e in eng.rebuild_from_trades([trade])]
    print("determinism", a == b)
    before = len(eng.ledger)
    eng.process_trades([trade])
    print("no_dup", before == len(eng.ledger))

    print("--- ledger ---")
    for e in entries:
        print(
            {
                "role": e.execution_role,
                "qty": str(e.executed_quantity),
                "exec_px": str(e.execution_price),
                "fee": str(e.fee_amount),
                "slip": str(e.slippage_amount),
                "spread": str(e.spread_cost),
                "gross": str(e.gross_realized_pnl),
                "net": str(e.net_realized_pnl),
                "mt": e.maker_taker,
                "mt_est": e.maker_taker_estimated,
                "assumptions": e.assumptions[:2],
            }
        )

    hand = hand_calc(cfg)
    print("--- hand calc ---")
    for k, v in hand.items():
        print(k, v)
    print(
        "hand_vs_engine_net",
        abs(hand["net"] - ts.net_realized_pnl) < Decimal("0.01"),
        hand["net"],
        ts.net_realized_pnl,
    )

    # slip disabled / spread disabled regression of fill qty (Phase 5.2.2 events unchanged)
    fills_before = [(e.event_id, e.price, e.quantity, e.timestamp.isoformat()) for e in trade.execution_events]
    cfg2 = ExecutionCostConfig(
        maker_fee_rate=Decimal("0.001"),
        taker_fee_rate=Decimal("0.001"),
        fee_source="user",
        slippage_policy="none",
        spread_policy="none",
    )
    eng2 = CostEngine(session_id="rp_qa2", config=cfg2)
    eng2.enable()
    eng2.process_trades([trade])
    fills_after = [(e.event_id, e.price, e.quantity, e.timestamp.isoformat()) for e in trade.execution_events]
    print("phase522_fills_unchanged", fills_before == fills_after)


if __name__ == "__main__":
    main()
