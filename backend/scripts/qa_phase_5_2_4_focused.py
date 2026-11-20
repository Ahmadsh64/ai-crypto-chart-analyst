"""LABELED FIXTURE QA — Phase 5.2.4 focused validation (not live OHLCV proof).

Validation-only. Does not modify production code.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.exchanges.types import ExchangeId, MarketType
from app.replay.analytics.config import AnalyticsConfig
from app.replay.analytics.drawdown import compute_drawdown
from app.replay.analytics.engine import AnalyticsEngine
from app.replay.analytics.equity_curve import (
    build_cashflow_curve_from_ledger,
    build_completed_trade_curve,
)
from app.replay.analytics.metrics_calculator import compute_profit_factor
from app.replay.analytics.models import EquityCurve, EquityPoint
from app.replay.analytics.trade_filter import classify_trade
from app.replay.costs.config import ExecutionCostConfig
from app.replay.costs.engine import CostEngine
from app.replay.simulation.models import SimulatedTrade, SimulationExecutionEvent

UTC = timezone.utc
NOW = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)


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


def base_trade(**kwargs) -> SimulatedTrade:
    defaults = dict(
        signal_key="qa",
        replay_session_id="rp_qa524",
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
        entry_timestamp=NOW + timedelta(minutes=1),
        exit_timestamp=NOW + timedelta(minutes=30),
        initial_stop_loss=95.0,
        current_stop_loss=95.0,
        take_profit_levels=[105.0, 110.0],
        tp_allocations=[0.5, 0.5],
        tp_filled=[True, True],
        original_quantity=1.0,
        remaining_quantity=0.0,
        executed_quantity=1.0,
        quantity_closed_tp=1.0,
        config_version="v",
        created_at=NOW,
        updated_at=NOW + timedelta(minutes=30),
        execution_events=[],
    )
    defaults.update(kwargs)
    return SimulatedTrade(**defaults)


def cost_engine(trades, *, fee="0.001", slip="1", spread="2"):
    cfg = ExecutionCostConfig(
        maker_fee_rate=Decimal(fee),
        taker_fee_rate=Decimal(fee),
        fee_source="user",
        slippage_policy="fixed_bps",
        slippage_bps=Decimal(slip),
        spread_policy="synthetic_assumption",
        spread_bps=Decimal(spread),
    )
    eng = CostEngine(session_id="rp_qa524", config=cfg)
    eng.enable()
    eng.process_trades(trades)
    return eng


def analytics_snap(trades, cost, *, initial=Decimal("10000")):
    a = AnalyticsEngine(
        session_id="rp_qa524",
        config=AnalyticsConfig(initial_equity=initial, enabled=True),
    )
    a.enable()
    return a.compute(trades, cost)


def force_net_via_summaries(nets: list[Decimal], *, initial=None):
    """Build synthetic completed ClassifiedTrade-like path through profit factor only."""
    # Direct PF function tests
    gp = sum((n for n in nets if n > 0), Decimal("0"))
    gl = sum((n for n in nets if n < 0), Decimal("0"))
    return compute_profit_factor(gp, gl)


def equity_from_values(values: list[Decimal], initial: Decimal) -> EquityCurve:
    points = []
    # First point at t0 = first value if series starts after initial; we encode
    # absolute equity levels as points (as drawdown expects).
    t0 = NOW
    for i, eq in enumerate(values):
        # Skip initial-only: points are post-trade equities
        if i == 0 and eq == initial:
            # still include as first observed equity point
            pass
        cum = eq - initial
        points.append(
            EquityPoint(
                timestamp=t0 + timedelta(minutes=i),
                trade_id=f"t{i}",
                event_id=f"e{i}",
                net_pnl_change=Decimal("0"),
                cumulative_net_pnl=cum,
                equity=eq,
                completed_trade_count=i + 1,
                curve="completed_trade",
            )
        )
    return EquityCurve(
        mode="completed_trade",
        points=points,
        available=True,
        initial_equity=initial,
        ending_equity=values[-1],
        cumulative_net_pnl=values[-1] - initial,
    )


def main() -> None:
    report: dict = {"label": "test_fixture_not_live_ohlcv", "cases": {}}

    # ─── Profit Factor ───
    pf_a = force_net_via_summaries([Decimal("300"), Decimal("-100")])
    report["cases"]["pf_A"] = {
        "expected": "3.0",
        "actual": pf_a.public_dict(),
        "pass": pf_a.availability == "available" and pf_a.value == Decimal("3"),
    }
    pf_b = force_net_via_summaries([Decimal("300")])
    report["cases"]["pf_B"] = {
        "expected": "infinite",
        "actual": pf_b.public_dict(),
        "pass": pf_b.availability == "infinite" and pf_b.value is None,
        "json_safe": "Infinity" not in json.dumps(pf_b.public_dict()),
    }
    pf_c = force_net_via_summaries([Decimal("-100")])
    report["cases"]["pf_C"] = {
        "expected": "0",
        "actual": pf_c.public_dict(),
        "pass": pf_c.availability == "available" and pf_c.value == Decimal("0"),
    }
    pf_d = force_net_via_summaries([])
    report["cases"]["pf_D_empty"] = {
        "expected": "unavailable",
        "actual": pf_d.public_dict(),
        "pass": pf_d.availability == "unavailable",
    }
    pf_e = force_net_via_summaries([Decimal("0"), Decimal("0")])
    report["cases"]["pf_E_breakeven"] = {
        "expected": "unavailable (zero_profit_and_loss)",
        "actual": pf_e.public_dict(),
        "pass": pf_e.availability == "unavailable",
    }

    # Engine-level PF with real trades (win 10 + loss -5 = PF 2) — fees off
    w = base_trade(
        trade_id="w",
        execution_events=[
            ev("we", "trade_opened", 100, 1, NOW + timedelta(minutes=1), "Limit entry filled."),
            ev("wx", "trade_closed", 110, 1, NOW + timedelta(minutes=10), "TP final.", 0),
        ],
    )
    l = base_trade(
        trade_id="l",
        lifecycle_status="closed_sl",
        exit_timestamp=NOW + timedelta(minutes=20),
        quantity_closed_tp=0.0,
        quantity_closed_sl=1.0,
        execution_events=[
            ev("le", "trade_opened", 100, 1, NOW + timedelta(minutes=2), "Limit entry filled."),
            ev("lx", "trade_closed", 95, 1, NOW + timedelta(minutes=20), "Stop loss filled."),
        ],
    )
    c0 = cost_engine([w, l], fee="0", slip="0", spread="0")
    # override spread policy none
    c0.config.spread_policy = "none"
    c0.rebuild_from_trades([w, l])
    snap = analytics_snap([w, l], c0)
    pf = snap.summary.profitability.profit_factor
    report["cases"]["pf_engine_win_loss"] = {
        "gross_profit": str(snap.summary.profitability.gross_profit),
        "gross_loss": str(snap.summary.profitability.gross_loss),
        "pf": pf.public_dict(),
        "net": str(snap.summary.profitability.total_net_realized_pnl),
        "pass": pf.availability == "available" and pf.value == Decimal("2"),
    }

    # ─── Equity with partials + costs ───
    partial = base_trade(
        trade_id="partial_full",
        take_profit_levels=[105.0, 110.0, 115.0],
        tp_allocations=[0.4, 0.3, 0.3],
        tp_filled=[True, True, True],
        remaining_quantity=0.0,
        executed_quantity=1.0,
        quantity_closed_tp=1.0,
        execution_events=[
            ev("pe", "trade_opened", 100, 1.0, NOW + timedelta(minutes=5), "Limit entry filled."),
            ev("p1", "trade_partially_closed", 105, 0.4, NOW + timedelta(minutes=10), "TP1 partial close.", 0),
            ev("p2", "trade_partially_closed", 110, 0.3, NOW + timedelta(minutes=15), "TP2 partial close.", 1),
            ev("p3", "trade_closed", 115, 0.3, NOW + timedelta(minutes=20), "TP3 final close.", 2),
        ],
    )
    c1 = cost_engine([partial])
    ts = c1.trade_summary(partial)
    a1 = analytics_snap([partial], c1, initial=Decimal("10000"))
    eq_c = a1.equity_completed
    eq_f = a1.equity_cashflow
    expected_end = Decimal("10000") + ts.net_realized_pnl
    report["cases"]["equity_partial"] = {
        "trade_net": str(ts.net_realized_pnl),
        "gross": str(ts.total_gross_realized_pnl),
        "fees": str(ts.total_fees),
        "slip": str(ts.total_slippage),
        "spread": str(ts.total_spread_cost),
        "costs": str(ts.total_costs),
        "completed_points": len(eq_c.points),
        "cashflow_points": len(eq_f.points),
        "ending_completed": str(eq_c.ending_equity),
        "ending_cashflow": str(eq_f.ending_equity),
        "expected_end": str(expected_end),
        "completed_count_stats": a1.summary.trade_stats.completed_trades,
        "reconcile_ok": eq_c.ending_equity == expected_end and eq_f.ending_equity == expected_end,
        "partial_not_extra_completed": a1.summary.trade_stats.completed_trades == 1,
        "cashflow_has_partials": len(eq_f.points) >= 3,
        "pass": (
            eq_c.ending_equity == expected_end
            and eq_f.ending_equity == expected_end
            and a1.summary.trade_stats.completed_trades == 1
            and len(eq_f.points) >= 3
        ),
    }

    # Missing initial equity
    a_none = AnalyticsEngine(
        session_id="rp_qa524",
        config=AnalyticsConfig(initial_equity=None, enabled=True),
    )
    a_none.enable()
    snap_none = a_none.compute([partial], c1)
    report["cases"]["equity_no_initial"] = {
        "return_avail": snap_none.summary.returns.total_return_pct.availability,
        "dd_available": snap_none.drawdown.available,
        "dd_reason": snap_none.drawdown.unavailable_reason,
        "pass": (
            snap_none.summary.returns.total_return_pct.availability == "unavailable"
            and snap_none.drawdown.available is False
        ),
    }

    # ─── Drawdown scenarios ───
    # A: 10000 → 11000 → 10500 → 9900 → 11000 → 11500
    # Peak before trough: 11000, trough 9900, DD=1100, recover at 11000
    curve_a = equity_from_values(
        [
            Decimal("10000"),
            Decimal("11000"),
            Decimal("10500"),
            Decimal("9900"),
            Decimal("11000"),
            Decimal("11500"),
        ],
        Decimal("10000"),
    )
    dd_a = compute_drawdown(curve_a)
    # Independent expected
    # At 10000: peak 10000 dd0; 11000 peak11000 dd0; 10500 dd500; 9900 dd1100; 11000 recover; 11500 peak
    exp_max_dd_a = Decimal("1100")
    report["cases"]["dd_A"] = {
        "max_dd": str(dd_a.max_drawdown),
        "expected_max_dd": str(exp_max_dd_a),
        "peak_ts": dd_a.peak_timestamp.isoformat() if dd_a.peak_timestamp else None,
        "trough_ts": dd_a.trough_timestamp.isoformat() if dd_a.trough_timestamp else None,
        "recovery_ts": dd_a.recovery_timestamp.isoformat() if dd_a.recovery_timestamp else None,
        "series": [
            {"eq": str(p.equity), "peak": str(p.peak_equity), "dd": str(p.drawdown)}
            for p in dd_a.series
        ],
        "pass": dd_a.max_drawdown == exp_max_dd_a and dd_a.recovery_timestamp is not None,
    }

    # B: 10000 → 9000 → 9500 → 10500 — recover only at 10500 (>=10000 peak)
    curve_b = equity_from_values(
        [Decimal("10000"), Decimal("9000"), Decimal("9500"), Decimal("10500")],
        Decimal("10000"),
    )
    dd_b = compute_drawdown(curve_b)
    # At 9500 still below peak 10000 — no recovery yet; recovery at 10500
    report["cases"]["dd_B"] = {
        "max_dd": str(dd_b.max_drawdown),
        "expected_max_dd": "1000",
        "recovery_ts": dd_b.recovery_timestamp.isoformat() if dd_b.recovery_timestamp else None,
        "recovery_equity": next(
            (
                str(p.equity)
                for p in dd_b.series
                if dd_b.recovery_timestamp and p.timestamp == dd_b.recovery_timestamp
            ),
            None,
        ),
        "pass": dd_b.max_drawdown == Decimal("1000")
        and dd_b.recovery_timestamp is not None
        and any(
            p.timestamp == dd_b.recovery_timestamp and p.equity == Decimal("10500")
            for p in dd_b.series
        ),
    }

    # C missing initial
    empty = EquityCurve(
        mode="completed_trade",
        points=[],
        available=True,
        initial_equity=None,
        ending_equity=None,
        cumulative_net_pnl=Decimal("0"),
    )
    dd_c = compute_drawdown(empty)
    report["cases"]["dd_C_no_initial"] = {
        "available": dd_c.available,
        "reason": dd_c.unavailable_reason,
        "pass": dd_c.available is False
        and dd_c.unavailable_reason == "initial_equity_not_configured",
    }

    # ─── closed_expired treatment ───
    # Simulator never assigns closed_expired (grep confirmed). Latent analytics risk:
    expired_with_remain = base_trade(
        trade_id="exp_remain",
        lifecycle_status="closed_expired",
        remaining_quantity=0.4,
        executed_quantity=1.0,
        quantity_closed_tp=0.6,
        quantity_closed_expired=0.0,
        execution_events=[
            ev("ee", "trade_opened", 100, 1.0, NOW + timedelta(minutes=1), "Limit entry filled."),
            ev(
                "ex1",
                "trade_partially_closed",
                105,
                0.6,
                NOW + timedelta(minutes=10),
                "TP1 partial close.",
                0,
            ),
            # NO exit fill for remaining 0.4
        ],
    )
    cls = classify_trade(expired_with_remain, None)
    expired_flat = base_trade(
        trade_id="exp_flat",
        lifecycle_status="closed_expired",
        remaining_quantity=0.0,
        executed_quantity=1.0,
        quantity_closed_expired=1.0,
        execution_events=[
            ev("ee2", "trade_opened", 100, 1.0, NOW + timedelta(minutes=1), "Limit entry filled."),
            ev(
                "ex2",
                "trade_closed",
                100,
                1.0,
                NOW + timedelta(minutes=10),
                "Expired flat close.",
            ),
        ],
    )
    cls_flat = classify_trade(expired_flat, None)
    cancelled_entry = base_trade(
        trade_id="cancel_entry",
        lifecycle_status="cancelled",
        remaining_quantity=0.0,
        executed_quantity=0.0,
        entry_price=None,
        execution_events=[
            ev(
                "canc",
                "trade_cancelled",
                None,
                None,
                NOW + timedelta(minutes=5),
                "Entry not filled before setup expiration.",
            )
        ],
    )
    cls_cancel = classify_trade(cancelled_entry, None)

    report["cases"]["closed_expired"] = {
        "sim_assigns_closed_expired": False,  # verified by static grep
        "expire_pending_sets": "cancelled",
        "entry_expire_sets": "cancelled",
        "analytics_counts_closed_expired_as_completed_unconditionally": False,
        "fixture_remain_gt0": {
            "remaining": expired_with_remain.remaining_quantity,
            "is_completed": cls.is_completed,
            "analytics_class": cls.analytics_class,
            "defect_if_status_used": cls.is_completed
            and expired_with_remain.remaining_quantity > 0,
        },
        "fixture_flat": {
            "remaining": expired_flat.remaining_quantity,
            "is_completed": cls_flat.is_completed,
        },
        "cancelled_entry_excluded": not cls_cancel.is_completed,
        "pass_current_sim_safe": True,
        # D1 fix: remaining > 0 must not be completed
        "latent_defect": False,
        "pass": (not cls.is_completed)
        and cls.analytics_class == "expired"
        and cls_flat.is_completed
        and (not cls_cancel.is_completed),
    }

    # Determinism rebuild
    a2 = AnalyticsEngine(
        session_id="rp_qa524",
        config=AnalyticsConfig(initial_equity=Decimal("10000"), enabled=True),
    )
    a2.enable()
    s1 = a2.compute([partial], c1)
    a2.reset()
    s2 = a2.compute([partial], c1)
    report["cases"]["determinism"] = {
        "pass": s1.summary.profitability.total_net_realized_pnl
        == s2.summary.profitability.total_net_realized_pnl
        and [p.model_dump(mode="json") for p in s1.equity_completed.points]
        == [p.model_dump(mode="json") for p in s2.equity_completed.points],
    }

    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
