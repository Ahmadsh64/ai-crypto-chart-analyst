"""Phase 5.2.3 E2E: real Binance OHLCV replay + costs reconciliation.

Labeled as a QA script (not production). Uses live public market data via the
existing replay loader — does not inject fabricated candles into production code.
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from datetime import datetime, timedelta, timezone

from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.replay.costs.config import ExecutionCostConfig
from app.replay.manager import get_replay_manager, reset_replay_manager
from app.replay.session import ReplaySession


UTC = timezone.utc


async def main() -> dict:
    reset_replay_manager()
    end = datetime.now(UTC)
    start = end - timedelta(days=3)
    session = ReplaySession(
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        start_time=start,
        end_time=end,
        timeframes=(Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4),
    )
    await session.load()
    assert session.event_times, "No replay events loaded from exchange"

    # Deterministic cost config for reconciliation
    cfg = ExecutionCostConfig(
        maker_fee_rate=Decimal("0.001"),
        taker_fee_rate=Decimal("0.001"),
        fee_source="user",
        fee_schedule_version="qa-user-v1",
        slippage_policy="fixed_bps",
        slippage_bps=Decimal("1"),
        spread_policy="synthetic_assumption",
        spread_bps=Decimal("2"),
        maker_taker_fallback="assume_taker",
    )
    await session.update_cost_config(cfg)

    await session.enable_analysis()
    # enable_costs also enables simulation
    await session.enable_costs()

    # Step through up to N events looking for closed trades with costs
    max_steps = min(400, len(session.event_times) - 1)
    for _ in range(max_steps):
        if session.event_index >= len(session.event_times) - 1:
            break
        await session.step()

    trades = list(session.simulator.trades.values())
    closed = [
        t
        for t in trades
        if t.lifecycle_status in {"closed_tp", "closed_sl", "closed_expired", "partially_closed"}
        and session.cost_engine.ledger.for_trade(t.trade_id)
    ]

    # Prefer fully closed
    fully = [t for t in closed if t.remaining_quantity <= 1e-12]
    pick = fully[0] if fully else (closed[0] if closed else None)

    summary = session.cost_engine.session_summary(trades)
    result: dict = {
        "session_id": session.session_id,
        "event_count": len(session.event_times),
        "steps": session.event_index,
        "sim_trade_count": len(trades),
        "cost_ledger_count": len(session.cost_engine.ledger),
        "session_summary": {
            "gross": str(summary.gross_realized_pnl),
            "entry_fees": str(summary.total_entry_fees),
            "exit_fees": str(summary.total_exit_fees),
            "fees": str(summary.total_fees),
            "slippage": str(summary.total_slippage),
            "spread": str(summary.total_spread_cost),
            "total_costs": str(summary.total_costs),
            "net": str(summary.net_realized_pnl),
            "fee_source": summary.fee_config_source,
            "assumptions": summary.assumptions[:5],
            "warnings": summary.warnings[:5],
        },
        "picked_trade": None,
        "reconciliation": None,
        "determinism": None,
        "duplicate_check": None,
        "fills_unchanged_when_costs_disabled": None,
    }

    if pick is not None:
        ts = session.cost_engine.trade_summary(pick)
        entries = session.cost_engine.ledger.for_trade(pick.trade_id)
        # Independent reconciliation from ledger rows
        gross = sum((e.gross_realized_pnl or Decimal("0") for e in entries), Decimal("0"))
        fees = sum((e.fee_amount for e in entries), Decimal("0"))
        slip = sum((e.slippage_amount for e in entries), Decimal("0"))
        spread = sum((e.spread_cost for e in entries), Decimal("0"))
        total_costs = fees + slip + spread
        # Trade summary net already accounts for allocation; compare formula
        expected_net = ts.total_gross_realized_pnl - ts.total_costs
        result["picked_trade"] = {
            "trade_id": pick.trade_id,
            "direction": pick.direction,
            "status": pick.lifecycle_status,
            "entry_price": pick.entry_price,
            "original_qty": pick.original_quantity,
            "remaining_qty": pick.remaining_quantity,
            "events": [
                {
                    "type": e.event_type,
                    "price": e.price,
                    "qty": e.quantity,
                    "reason": e.reason,
                }
                for e in pick.execution_events
            ],
            "ledger": [
                {
                    "role": e.execution_role,
                    "mt": e.maker_taker,
                    "ref": str(e.reference_price),
                    "exec": str(e.execution_price),
                    "qty": str(e.executed_quantity),
                    "fee": str(e.fee_amount),
                    "slip": str(e.slippage_amount),
                    "spread": str(e.spread_cost),
                    "gross": str(e.gross_realized_pnl) if e.gross_realized_pnl is not None else None,
                    "alloc_entry_fee": str(e.allocated_entry_fee)
                    if e.allocated_entry_fee is not None
                    else None,
                    "net": str(e.net_realized_pnl) if e.net_realized_pnl is not None else None,
                    "assumptions": e.assumptions[:2],
                }
                for e in entries
            ],
            "trade_summary": {
                "gross": str(ts.total_gross_realized_pnl),
                "entry_fees": str(ts.total_entry_fees),
                "exit_fees": str(ts.total_exit_fees),
                "fees": str(ts.total_fees),
                "slippage": str(ts.total_slippage),
                "spread": str(ts.total_spread_cost),
                "total_costs": str(ts.total_costs),
                "net": str(ts.net_realized_pnl),
            },
        }
        result["reconciliation"] = {
            "ledger_sum_fees": str(fees),
            "ledger_sum_slip": str(slip),
            "ledger_sum_spread": str(spread),
            "ledger_sum_gross_exit": str(gross),
            "ledger_total_costs": str(total_costs),
            "summary_total_costs": str(ts.total_costs),
            "summary_net": str(ts.net_realized_pnl),
            "expected_net_gross_minus_costs": str(expected_net),
            "costs_match": abs(total_costs - ts.total_costs) < Decimal("0.0001"),
            "net_matches_gross_minus_costs": abs(expected_net - ts.net_realized_pnl)
            < Decimal("0.0001"),
            "remaining_zero": pick.remaining_quantity <= 1e-12,
        }

        # Determinism: rebuild costs twice
        a = [
            (e.execution_id, str(e.fee_amount), str(e.net_realized_pnl))
            for e in session.cost_engine.rebuild_from_trades(trades)
        ]
        b = [
            (e.execution_id, str(e.fee_amount), str(e.net_realized_pnl))
            for e in session.cost_engine.rebuild_from_trades(trades)
        ]
        result["determinism"] = {"identical_rebuild": a == b, "entries": len(a)}

        # Duplicate processing
        before = len(session.cost_engine.ledger)
        session.cost_engine.process_trades(trades)
        after = len(session.cost_engine.ledger)
        result["duplicate_check"] = {"before": before, "after": after, "ok": before == after}

        # Disabling costs leaves fills unchanged
        fill_fingerprint = [
            (t.trade_id, t.entry_price, t.remaining_quantity, len(t.execution_events))
            for t in trades
        ]
        session.cost_engine.disable()
        fill_after = [
            (t.trade_id, t.entry_price, t.remaining_quantity, len(t.execution_events))
            for t in session.simulator.trades.values()
        ]
        result["fills_unchanged_when_costs_disabled"] = fill_fingerprint == fill_after

    get_replay_manager()._sessions[session.session_id] = session
    return result


if __name__ == "__main__":
    out = asyncio.run(main())
    print(json.dumps(out, indent=2, default=str))
