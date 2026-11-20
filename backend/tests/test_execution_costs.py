"""Phase 5.2.3 — Fees, Slippage & Execution Cost Engine tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.exchanges.types import ExchangeId, MarketType
from app.main import app
from app.replay.costs.config import ExecutionCostConfig, FeeSchedule
from app.replay.costs.engine import CostEngine
from app.replay.costs.fee_calculator import applicable_fee_rate, calculate_fee
from app.replay.costs.pnl_calculator import allocate_entry_fee, gross_pnl, net_pnl
from app.replay.costs.slippage_calculator import apply_slippage
from app.replay.costs.spread_calculator import apply_half_spread
from app.replay.manager import reset_replay_manager
from app.replay.simulation.models import SimulatedTrade, SimulationExecutionEvent

UTC = timezone.utc
EX = ExchangeId.BINANCE


def _ts(i: int = 0) -> datetime:
    return datetime(2024, 1, 1, 12, 0, tzinfo=UTC) + timedelta(minutes=5 * i)


def _trade(**kwargs) -> SimulatedTrade:
    now = _ts(0)
    base = dict(
        trade_id="st_test1",
        signal_key="sig1",
        replay_session_id="rp_test",
        exchange=EX,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        direction="LONG",
        decision="LONG",
        decision_timestamp=now,
        decision_event_index=0,
        lifecycle_status="open",
        entry_limit_price=100.0,
        entry_price=100.0,
        entry_timestamp=_ts(1),
        initial_stop_loss=95.0,
        current_stop_loss=95.0,
        take_profit_levels=[105.0, 110.0, 115.0],
        tp_allocations=[0.4, 0.3, 0.3],
        tp_filled=[False, False, False],
        original_quantity=1.0,
        remaining_quantity=1.0,
        executed_quantity=1.0,
        config_version="trade-sim-v1.0.0",
        created_at=now,
        updated_at=now,
        execution_events=[],
    )
    base.update(kwargs)
    return SimulatedTrade(**base)


def _ev(
    eid: str,
    etype: str,
    *,
    price: float,
    qty: float,
    ts: datetime | None = None,
    tp_index: int | None = None,
    reason: str | None = None,
) -> SimulationExecutionEvent:
    return SimulationExecutionEvent(
        event_id=eid,
        event_type=etype,  # type: ignore[arg-type]
        timestamp=ts or _ts(1),
        price=price,
        quantity=qty,
        tp_index=tp_index,
        reason=reason,
    )


# ─── Fees ───


def test_maker_and_taker_fee():
    sch = FeeSchedule(
        exchange=EX,
        market_type=MarketType.SPOT,
        maker_fee_rate=Decimal("0.001"),
        taker_fee_rate=Decimal("0.002"),
        source="user",
    )
    rm, cm, _ = applicable_fee_rate("maker", sch, fallback="assume_taker")
    rt, ct, _ = applicable_fee_rate("taker", sch, fallback="assume_taker")
    assert rm == Decimal("0.001") and cm == "maker"
    assert rt == Decimal("0.002") and ct == "taker"
    assert calculate_fee(Decimal("1000"), rm) == Decimal("1.00000000")


def test_zero_fee():
    assert calculate_fee(Decimal("500"), Decimal("0")) == Decimal("0.00000000")


def test_negative_fee_rejected():
    with pytest.raises(Exception):
        FeeSchedule(
            exchange=EX,
            market_type=MarketType.SPOT,
            maker_fee_rate=Decimal("-0.1"),
            taker_fee_rate=Decimal("0.1"),
        )


def test_fee_fallback_assume_taker():
    sch = FeeSchedule(
        exchange=EX,
        market_type=MarketType.SPOT,
        maker_fee_rate=Decimal("0.001"),
        taker_fee_rate=Decimal("0.002"),
    )
    rate, klass, warns = applicable_fee_rate("unknown", sch, fallback="assume_taker")
    assert rate == Decimal("0.002")
    assert klass == "taker"
    assert warns


def test_user_configured_fee_source():
    cfg = ExecutionCostConfig(
        maker_fee_rate=Decimal("0.0005"),
        taker_fee_rate=Decimal("0.0007"),
        fee_source="user",
    )
    sch = cfg.resolve_fee_schedule(EX, MarketType.SPOT)
    assert sch.source == "user"
    assert sch.maker_fee_rate == Decimal("0.0005")


# ─── Slippage ───


def test_slippage_none():
    cfg = ExecutionCostConfig(slippage_policy="none")
    px, cost, _ = apply_slippage(
        Decimal("100"), direction="LONG", role="entry", config=cfg
    )
    assert px == Decimal("100")
    assert cost == 0


def test_slippage_long_entry_adverse():
    cfg = ExecutionCostConfig(slippage_policy="fixed_bps", slippage_bps=Decimal("10"))
    px, delta, _ = apply_slippage(
        Decimal("100"), direction="LONG", role="entry", config=cfg
    )
    assert px > Decimal("100")
    assert delta > 0


def test_slippage_long_exit_adverse():
    cfg = ExecutionCostConfig(slippage_policy="fixed_bps", slippage_bps=Decimal("10"))
    px, delta, _ = apply_slippage(
        Decimal("100"), direction="LONG", role="exit", config=cfg
    )
    assert px < Decimal("100")


def test_slippage_short_entry_adverse():
    cfg = ExecutionCostConfig(slippage_policy="percentage", slippage_percentage=Decimal("0.01"))
    px, _, _ = apply_slippage(
        Decimal("100"), direction="SHORT", role="entry", config=cfg
    )
    assert px < Decimal("100")


def test_slippage_short_exit_adverse():
    cfg = ExecutionCostConfig(slippage_policy="fixed_bps", slippage_bps=Decimal("10"))
    px, _, _ = apply_slippage(
        Decimal("100"), direction="SHORT", role="exit", config=cfg
    )
    assert px > Decimal("100")


def test_slippage_deterministic():
    cfg = ExecutionCostConfig(slippage_policy="fixed_bps", slippage_bps=Decimal("5"))
    a = apply_slippage(Decimal("200"), direction="LONG", role="entry", config=cfg)
    b = apply_slippage(Decimal("200"), direction="LONG", role="entry", config=cfg)
    assert a == b


# ─── Spread ───


def test_spread_disabled():
    cfg = ExecutionCostConfig(spread_policy="none")
    px, half, assump, _ = apply_half_spread(
        Decimal("100"), direction="LONG", role="entry", config=cfg
    )
    assert px == Decimal("100")
    assert half == 0
    assert not assump


def test_spread_synthetic_labeled():
    cfg = ExecutionCostConfig(spread_policy="synthetic_assumption", spread_bps=Decimal("10"))
    px, half, assump, _ = apply_half_spread(
        Decimal("100"), direction="LONG", role="entry", config=cfg
    )
    assert px > Decimal("100")
    assert half > 0
    assert any("SYNTHETIC" in a for a in assump)


def test_spread_exit_direction_long():
    cfg = ExecutionCostConfig(spread_policy="fixed_bps", spread_bps=Decimal("10"))
    px, _, _, _ = apply_half_spread(
        Decimal("100"), direction="LONG", role="exit", config=cfg
    )
    assert px < Decimal("100")


# ─── P&L ───


def test_gross_long_profit_loss():
    assert gross_pnl(
        direction="LONG",
        entry_price=Decimal("100"),
        exit_price=Decimal("110"),
        quantity=Decimal("2"),
    ) == Decimal("20.00000000")
    assert gross_pnl(
        direction="LONG",
        entry_price=Decimal("100"),
        exit_price=Decimal("90"),
        quantity=Decimal("1"),
    ) == Decimal("-10.00000000")


def test_gross_short_profit_loss():
    assert gross_pnl(
        direction="SHORT",
        entry_price=Decimal("100"),
        exit_price=Decimal("90"),
        quantity=Decimal("1"),
    ) == Decimal("10.00000000")
    assert gross_pnl(
        direction="SHORT",
        entry_price=Decimal("100"),
        exit_price=Decimal("110"),
        quantity=Decimal("1"),
    ) == Decimal("-10.00000000")


def test_entry_fee_allocation_no_double_count():
    total = Decimal("10")
    a = allocate_entry_fee(total, exit_qty=Decimal("0.4"), original_qty=Decimal("1"))
    b = allocate_entry_fee(total, exit_qty=Decimal("0.6"), original_qty=Decimal("1"))
    assert a + b == Decimal("10.00000000")


def test_net_pnl_formula():
    net = net_pnl(
        gross=Decimal("10"),
        entry_fee_allocated=Decimal("1"),
        exit_fee=Decimal("1"),
        slippage_cost=Decimal("0.5"),
        spread_cost=Decimal("0.5"),
    )
    assert net == Decimal("7.00000000")


# ─── Engine / ledger ───


def test_engine_partial_exits_and_unique_ids():
    cfg = ExecutionCostConfig(
        maker_fee_rate=Decimal("0.001"),
        taker_fee_rate=Decimal("0.001"),
        fee_source="user",
        slippage_policy="none",
        spread_policy="none",
    )
    engine = CostEngine(session_id="rp_test", config=cfg)
    engine.enable()
    trade = _trade(
        lifecycle_status="closed_tp",
        remaining_quantity=0.0,
        tp_filled=[True, True, True],
        quantity_closed_tp=1.0,
        execution_events=[
            _ev("se_open", "trade_opened", price=100.0, qty=1.0, ts=_ts(1)),
            _ev(
                "se_tp1",
                "trade_partially_closed",
                price=105.0,
                qty=0.4,
                ts=_ts(2),
                tp_index=0,
                reason="TP1 partial close.",
            ),
            _ev(
                "se_tp2",
                "trade_partially_closed",
                price=110.0,
                qty=0.3,
                ts=_ts(3),
                tp_index=1,
                reason="TP2 partial close.",
            ),
            _ev(
                "se_tp3",
                "trade_closed",
                price=115.0,
                qty=0.3,
                ts=_ts(4),
                tp_index=2,
                reason="TP3 final close.",
            ),
        ],
    )
    entries = engine.process_trades([trade])
    assert len(entries) == 4
    ids = [e.execution_id for e in entries]
    assert len(ids) == len(set(ids))
    # Duplicate rejection
    again = engine.process_trades([trade])
    assert again == []
    summary = engine.trade_summary(trade)
    assert summary.total_gross_realized_pnl > 0
    assert summary.total_entry_fees > 0
    assert summary.total_exit_fees > 0
    # Entry fees allocated once across exits
    allocated = sum(
        (e.allocated_entry_fee or Decimal("0") for e in engine.ledger.for_trade(trade.trade_id) if e.execution_role == "exit"),
        Decimal("0"),
    )
    assert abs(allocated - summary.total_entry_fees) < Decimal("0.0001")
    assert summary.net_realized_pnl == summary.total_gross_realized_pnl - summary.total_costs


def test_engine_sl_exit():
    cfg = ExecutionCostConfig(
        maker_fee_rate=Decimal("0"),
        taker_fee_rate=Decimal("0"),
        fee_source="user",
        slippage_policy="none",
        spread_policy="none",
    )
    engine = CostEngine(session_id="rp_test", config=cfg)
    engine.enable()
    trade = _trade(
        lifecycle_status="closed_sl",
        remaining_quantity=0.0,
        quantity_closed_sl=1.0,
        execution_events=[
            _ev("se_o", "trade_opened", price=100.0, qty=1.0),
            _ev("se_sl", "trade_closed", price=95.0, qty=1.0, reason="Stop loss filled."),
        ],
    )
    engine.process_trades([trade])
    s = engine.trade_summary(trade)
    assert s.total_gross_realized_pnl == Decimal("-5.00000000")
    assert s.net_realized_pnl == Decimal("-5.00000000")


def test_rebuild_deterministic():
    cfg = ExecutionCostConfig(
        maker_fee_rate=Decimal("0.001"),
        taker_fee_rate=Decimal("0.001"),
        fee_source="user",
        slippage_policy="fixed_bps",
        slippage_bps=Decimal("1"),
        spread_policy="none",
    )
    trade = _trade(
        lifecycle_status="closed_tp",
        remaining_quantity=0.0,
        execution_events=[
            _ev("se_o", "trade_opened", price=100.0, qty=1.0),
            _ev("se_c", "trade_closed", price=110.0, qty=1.0, tp_index=0, reason="TP1"),
        ],
    )

    def run():
        eng = CostEngine(session_id="rp_det", config=cfg.model_copy(deep=True))
        eng.enable()
        eng.rebuild_from_trades([trade])
        s = eng.trade_summary(trade)
        return (
            str(s.total_gross_realized_pnl),
            str(s.total_fees),
            str(s.total_slippage),
            str(s.net_realized_pnl),
            len(eng.ledger),
        )

    assert run() == run()


def test_disabling_costs_does_not_require_sim_change():
    trade = _trade(
        execution_events=[_ev("se_o", "trade_opened", price=100.0, qty=1.0)]
    )
    eng = CostEngine(session_id="rp", config=ExecutionCostConfig())
    # disabled — no entries
    assert eng.process_trades([trade]) == []
    eng.enable()
    assert len(eng.process_trades([trade])) == 1


# ─── API ───


@pytest.fixture
def client():
    reset_replay_manager()
    yield TestClient(app)
    reset_replay_manager()


def test_costs_api_enable_config_ledger(client: TestClient, monkeypatch):
    from app.replay.manager import get_replay_manager
    from app.replay.session import ReplaySession
    from app.exchanges.types import Candle, Timeframe
    from app.replay.timeline import build_event_timeline, candle_close_time

    start = _ts(0)
    end = start + timedelta(hours=1)

    def candle(i: int) -> Candle:
        open_ts = start + timedelta(minutes=5 * i)
        return Candle(
            timestamp=open_ts,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1.0,
            exchange=EX,
            symbol="BTC/USDT",
            market_type=MarketType.SPOT,
            is_closed=True,
            close_time=open_ts + timedelta(seconds=300) - timedelta(milliseconds=1),
        )

    m5 = [candle(i) for i in range(8)]
    sess = ReplaySession(
        exchange=EX,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        start_time=start,
        end_time=end,
    )
    sess.series_by_tf = {
        Timeframe.M5: m5,
        Timeframe.M15: m5[:1],
        Timeframe.H1: m5[:1],
        Timeframe.H4: m5[:1],
    }
    sess.event_times = build_event_timeline(sess.series_by_tf, start=start, end=end)
    assert sess.event_times
    sess.status = "ready"
    get_replay_manager()._sessions[sess.session_id] = sess
    sid = sess.session_id

    # Seed a simulated trade with fills (bypass analysis pipeline)
    trade = _trade(
        replay_session_id=sid,
        lifecycle_status="closed_tp",
        remaining_quantity=0.0,
        execution_events=[
            _ev("se_api_o", "trade_opened", price=100.0, qty=1.0, ts=sess.event_times[0]),
            _ev(
                "se_api_c",
                "trade_closed",
                price=110.0,
                qty=1.0,
                ts=sess.event_times[min(1, len(sess.event_times) - 1)],
                reason="TP1",
            ),
        ],
    )
    sess.simulator.trades[trade.trade_id] = trade
    sess.simulator.enable()

    async def fake_analysis(*, emit: bool = True):
        return None

    monkeypatch.setattr(sess, "_run_analysis_unlocked", fake_analysis)
    monkeypatch.setattr(sess, "_run_simulation_unlocked", fake_analysis)

    r = client.post(f"/api/v1/replay/sessions/{sid}/costs/enable")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["costs_enabled"] is True
    assert "NOT REAL EXECUTION" in body["snapshot"]["disclaimer"]

    r2 = client.get(f"/api/v1/replay/sessions/{sid}/costs")
    assert r2.status_code == 200
    assert r2.json()["snapshot"]["summary"]["ledger_entry_count"] >= 2

    r3 = client.put(
        f"/api/v1/replay/sessions/{sid}/costs/config",
        json={"maker_fee_rate": 0.0005, "taker_fee_rate": 0.0005, "slippage_policy": "none"},
    )
    assert r3.status_code == 200, r3.text
    assert r3.json()["snapshot"]["summary"]["fee_config_source"] == "user"

    r4 = client.get(f"/api/v1/replay/sessions/{sid}/costs/ledger")
    assert r4.status_code == 200
    assert r4.json()["total"] >= 2

    r5 = client.get(f"/api/v1/replay/sessions/{sid}/costs/summary")
    assert r5.status_code == 200

    r6 = client.post(f"/api/v1/replay/sessions/{sid}/costs/disable")
    assert r6.status_code == 200
    assert r6.json()["costs_enabled"] is False
