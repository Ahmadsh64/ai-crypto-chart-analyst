"""Phase 5.2.2 — Historical Trade Simulation Engine tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.main import app
from app.replay.analysis.models import HistoricalAnalysisSnapshot
from app.replay.manager import reset_replay_manager
from app.replay.simulation.config import SimulationConfig
from app.replay.simulation.eligibility import (
    build_signal_key,
    derive_entry_limit_price,
    evaluate_eligibility,
)
from app.replay.simulation.entry_execution import try_fill_entry
from app.replay.simulation.exit_execution import resolve_same_candle_order
from app.replay.simulation.simulator import TradeSimulator
from app.replay.simulation.validation import quantities_conserved
from app.replay.timeline import candle_close_time

UTC = timezone.utc
EX = ExchangeId.BINANCE
SYM = "BTC/USDT"


def _ts(i: int = 0) -> datetime:
    return datetime(2024, 1, 1, 12, 0, tzinfo=UTC) + timedelta(minutes=5 * i)


def _candle(
    i: int,
    o: float,
    h: float,
    l: float,
    c: float,
    *,
    tf: Timeframe = Timeframe.M5,
    market_type: MarketType = MarketType.SPOT,
) -> Candle:
    open_ts = _ts(i)
    return Candle(
        timestamp=open_ts,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=1.0,
        exchange=EX,
        symbol=SYM,
        market_type=market_type,
        is_closed=True,
        close_time=open_ts + timedelta(seconds=300) - timedelta(milliseconds=1),
    )


def _snap(**kwargs) -> HistoricalAnalysisSnapshot:
    base = dict(
        session_id="rp_test",
        replay_timestamp=_ts(0),
        event_index=0,
        exchange=EX,
        symbol=SYM,
        market_type=MarketType.USDT_M_FUTURES,
        decision="LONG",
        decision_reason="test",
        lifecycle_status="active",
        direction="LONG",
        bullish_score=70.0,
        bearish_score=20.0,
        entry_zone={
            "entry_low": 99.0,
            "entry_high": 101.0,
            "entry_reference_price": 100.0,
        },
        stop_loss=95.0,
        take_profit_levels=[105.0, 110.0, 115.0],
        risk_reward=2.0,
        trade_plan_status="eligible",
        position_size=1.5,
        expires_at=_ts(20),
        decision_id="dec_1",
        trade_plan_id="plan_1",
        data_quality="ok",
        data_ready=True,
        config_version="hist-v1",
        analysis_timestamp=_ts(0),
    )
    base.update(kwargs)
    return HistoricalAnalysisSnapshot(**base)


# ─── Eligibility ───


def test_eligibility_long():
    r = evaluate_eligibility(_snap(), config=SimulationConfig())
    assert r.eligible
    assert r.direction == "LONG"
    assert r.entry_limit_price == 100.0


def test_eligibility_short_futures():
    r = evaluate_eligibility(
        _snap(
            decision="SHORT",
            direction="SHORT",
            stop_loss=105.0,
            take_profit_levels=[95.0, 90.0, 85.0],
            entry_zone={
                "entry_low": 99.0,
                "entry_high": 101.0,
                "entry_reference_price": 100.0,
            },
        ),
        config=SimulationConfig(),
    )
    assert r.eligible
    assert r.direction == "SHORT"


def test_eligibility_spot_short_rejected():
    r = evaluate_eligibility(
        _snap(market_type=MarketType.SPOT, decision="SHORT", direction="SHORT"),
        config=SimulationConfig(),
    )
    assert not r.eligible
    assert "Spot" in (r.rejection_reason or "")


@pytest.mark.parametrize("decision", ["WAIT", "NO_TRADE", "NO TRADE"])
def test_eligibility_wait_no_trade(decision: str):
    r = evaluate_eligibility(_snap(decision=decision), config=SimulationConfig())
    assert not r.eligible


def test_eligibility_missing_plan_fields():
    r = evaluate_eligibility(_snap(entry_zone=None), config=SimulationConfig())
    assert not r.eligible
    assert "entry zone" in (r.rejection_reason or "").lower()


def test_eligibility_invalid_sl():
    r = evaluate_eligibility(_snap(stop_loss=None), config=SimulationConfig())
    assert not r.eligible


def test_eligibility_invalid_tp():
    r = evaluate_eligibility(_snap(take_profit_levels=[]), config=SimulationConfig())
    assert not r.eligible


def test_eligibility_expired_lifecycle():
    r = evaluate_eligibility(
        _snap(lifecycle_status="expired"), config=SimulationConfig()
    )
    assert not r.eligible


def test_eligibility_insufficient_data():
    r = evaluate_eligibility(
        _snap(data_ready=False, data_quality="insufficient"),
        config=SimulationConfig(),
    )
    assert not r.eligible


def test_eligibility_missing_quantity():
    r = evaluate_eligibility(_snap(position_size=None), config=SimulationConfig())
    assert not r.eligible
    assert "position size" in (r.rejection_reason or "").lower()


def test_entry_policy_no_silent_midpoint():
    zone = {"entry_low": 99.0, "entry_high": 101.0}  # no reference
    assert (
        derive_entry_limit_price(zone, direction="LONG", policy="exact_reference_price")
        is None
    )
    mid = derive_entry_limit_price(zone, direction="LONG", policy="zone_midpoint")
    assert mid == 100.0


# ─── Entry execution ───


def test_long_limit_fill_at_limit():
    decision = candle_close_time(_candle(0, 100, 101, 99, 100.5), Timeframe.M5)
    # Opens above limit, dips to 99.5 — fills at limit 100.
    c = _candle(1, 102, 103, 99.5, 101)
    fill = try_fill_entry(
        direction="LONG",
        limit_price=100.0,
        stop_loss=95.0,
        take_profits=[105.0],
        candle=c,
        timeframe=Timeframe.M5,
        decision_timestamp=decision,
        expires_at=None,
        clock=candle_close_time(c, Timeframe.M5),
    )
    assert fill.filled
    assert fill.fill_price == 100.0


def test_short_limit_fill_at_limit():
    decision = candle_close_time(_candle(0, 100, 101, 99, 100), Timeframe.M5)
    # Opens below limit, rallies to 100.5 — fills at limit 100.
    c = _candle(1, 98, 100.5, 97, 99)
    fill = try_fill_entry(
        direction="SHORT",
        limit_price=100.0,
        stop_loss=105.0,
        take_profits=[95.0],
        candle=c,
        timeframe=Timeframe.M5,
        decision_timestamp=decision,
        expires_at=None,
        clock=candle_close_time(c, Timeframe.M5),
    )
    assert fill.filled
    assert fill.fill_price == 100.0


def test_long_gap_through_limit_fills_at_open():
    decision = candle_close_time(_candle(0, 100, 101, 99, 100), Timeframe.M5)
    c = _candle(1, 99.0, 101, 98.5, 100)
    fill = try_fill_entry(
        direction="LONG",
        limit_price=100.0,
        stop_loss=95.0,
        take_profits=[105.0],
        candle=c,
        timeframe=Timeframe.M5,
        decision_timestamp=decision,
        expires_at=None,
        clock=candle_close_time(c, Timeframe.M5),
    )
    assert fill.filled
    assert fill.fill_price == 99.0


def test_short_gap_through_limit_fills_at_open():
    decision = candle_close_time(_candle(0, 100, 101, 99, 100), Timeframe.M5)
    c = _candle(1, 101.0, 102, 99.5, 100.5)
    fill = try_fill_entry(
        direction="SHORT",
        limit_price=100.0,
        stop_loss=105.0,
        take_profits=[95.0],
        candle=c,
        timeframe=Timeframe.M5,
        decision_timestamp=decision,
        expires_at=None,
        clock=candle_close_time(c, Timeframe.M5),
    )
    assert fill.filled
    assert fill.fill_price == 101.0


def test_entry_never_reached():
    decision = candle_close_time(_candle(0, 100, 101, 99, 100), Timeframe.M5)
    # Entire range stays above the LONG limit (low > limit ⇒ high never "reaches" from above as a fill touch for limit buy: need high >= limit).
    c = _candle(1, 110, 112, 109, 111)
    fill = try_fill_entry(
        direction="LONG",
        limit_price=100.0,
        stop_loss=95.0,
        take_profits=[105.0],
        candle=c,
        timeframe=Timeframe.M5,
        decision_timestamp=decision,
        expires_at=None,
        clock=candle_close_time(c, Timeframe.M5),
    )
    assert not fill.filled
    assert c.low > 100.0


def test_entry_expiration():
    decision = candle_close_time(_candle(0, 100, 101, 99, 100), Timeframe.M5)
    c = _candle(5, 99, 101, 98, 100)
    fill = try_fill_entry(
        direction="LONG",
        limit_price=100.0,
        stop_loss=95.0,
        take_profits=[105.0],
        candle=c,
        timeframe=Timeframe.M5,
        decision_timestamp=decision,
        expires_at=_ts(2),
        clock=candle_close_time(c, Timeframe.M5),
    )
    assert fill.expired
    assert not fill.filled


def test_no_fill_on_decision_candle():
    c = _candle(0, 99, 101, 98, 100)
    close = candle_close_time(c, Timeframe.M5)
    fill = try_fill_entry(
        direction="LONG",
        limit_price=100.0,
        stop_loss=95.0,
        take_profits=[105.0],
        candle=c,
        timeframe=Timeframe.M5,
        decision_timestamp=close,
        expires_at=None,
        clock=close,
    )
    assert not fill.filled
    assert "at/before decision" in (fill.reason or "").lower()


# ─── Exit / ambiguity ───


def test_long_sl_and_tp_same_candle_conservative():
    c = _candle(1, 100, 106, 94, 101)
    result = resolve_same_candle_order(
        direction="LONG",
        candle=c,
        stop=95.0,
        pending_tps=[(0, 105.0)],
        policy="conservative_stop_first",
        lower_tf_candles=None,
        lower_tf=None,
    )
    assert len(result.hits) == 1
    assert result.hits[0].kind == "sl"
    assert "conservative_stop_first" in (result.ambiguity_warning or "")


def test_long_sl_and_tp_mark_ambiguous():
    c = _candle(1, 100, 106, 94, 101)
    result = resolve_same_candle_order(
        direction="LONG",
        candle=c,
        stop=95.0,
        pending_tps=[(0, 105.0)],
        policy="mark_ambiguous",
        lower_tf_candles=None,
        lower_tf=None,
    )
    assert result.ambiguous
    assert result.hits[0].kind == "sl"


def test_multiple_tp_same_candle():
    c = _candle(1, 100, 116, 99, 112)
    result = resolve_same_candle_order(
        direction="LONG",
        candle=c,
        stop=90.0,
        pending_tps=[(0, 105.0), (1, 110.0), (2, 115.0)],
        policy="conservative_stop_first",
        lower_tf_candles=None,
        lower_tf=None,
    )
    assert len(result.hits) == 1
    assert result.hits[0].tp_index == 0


def test_lower_tf_resolves_order():
    parent = _candle(0, 100, 106, 94, 101)
    # Inside parent: first touch TP then later SL — but we only have one TF granularity.
    # Use two synthetic lower bars (same TF window) sequenced by open time.
    bar1 = Candle(
        timestamp=_ts(0),
        open=100,
        high=106,
        low=99,
        close=105,
        volume=1,
        exchange=EX,
        symbol=SYM,
        market_type=MarketType.SPOT,
        is_closed=True,
        close_time=_ts(0) + timedelta(seconds=150) - timedelta(milliseconds=1),
    )
    bar2 = Candle(
        timestamp=_ts(0) + timedelta(seconds=150),
        open=105,
        high=105.5,
        low=94,
        close=95,
        volume=1,
        exchange=EX,
        symbol=SYM,
        market_type=MarketType.SPOT,
        is_closed=True,
        close_time=candle_close_time(parent, Timeframe.M5),
    )
    # Fake lower TF as M5 against parent M5 will include both if close times fit.
    result = resolve_same_candle_order(
        direction="LONG",
        candle=parent,
        stop=95.0,
        pending_tps=[(0, 105.0)],
        policy="use_lower_timeframe_if_available",
        lower_tf_candles=[bar1, bar2],
        lower_tf=Timeframe.M5,
    )
    # First lower bar hits TP before SL
    assert result.hits
    assert result.hits[0].kind == "tp"
    assert result.policy_applied == "use_lower_timeframe_if_available"


def test_stop_gap_long():
    c = _candle(1, 94.0, 96, 93, 95)
    result = resolve_same_candle_order(
        direction="LONG",
        candle=c,
        stop=95.0,
        pending_tps=[],
        policy="conservative_stop_first",
        lower_tf_candles=None,
        lower_tf=None,
    )
    assert result.hits[0].price == 94.0  # open through stop


# ─── Simulator integration ───


def test_duplicate_signal_prevention():
    sim = TradeSimulator(session_id="rp_test")
    sim.enable()
    c0 = _candle(0, 100, 101, 99, 100)
    clock0 = candle_close_time(c0, Timeframe.M5)
    # Decision timestamp = replay clock (candle close), so entry cannot fill on this bar.
    snap = _snap(replay_timestamp=clock0)
    e1 = sim.process_tick(
        analysis=snap,
        execution_candle=c0,
        series_by_tf={Timeframe.M5: [c0]},
        clock=clock0,
        event_index=0,
    )
    pending = [e for e in e1 if e.event_type == "trade_pending"]
    assert len(pending) == 1
    e2 = sim.process_tick(
        analysis=snap,
        execution_candle=c0,
        series_by_tf={Timeframe.M5: [c0]},
        clock=clock0,
        event_index=0,
    )
    assert not any(e.event_type == "trade_pending" for e in e2)
    assert len([t for t in sim.trades.values() if t.lifecycle_status == "pending_entry"]) == 1


def test_partial_tps_and_quantity_conservation():
    sim = TradeSimulator(session_id="rp_test")
    sim.enable()
    snap = _snap(replay_timestamp=candle_close_time(_candle(0, 100, 101, 99, 100), Timeframe.M5))
    candles = [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100.5, 100.8, 99.5, 100),  # fill at 100
        _candle(2, 104, 106, 103, 105),  # TP1
        _candle(3, 108, 111, 107, 110),  # TP2
        _candle(4, 112, 116, 111, 115),  # TP3
    ]
    for i, c in enumerate(candles):
        analysis = snap if i == 0 else None
        if i == 0:
            analysis = _snap(replay_timestamp=candle_close_time(c, Timeframe.M5), event_index=0)
        sim.process_tick(
            analysis=analysis,
            execution_candle=c,
            series_by_tf={Timeframe.M5: candles[: i + 1]},
            clock=candle_close_time(c, Timeframe.M5),
            event_index=i,
        )
    trades = [t for t in sim.trades.values() if t.lifecycle_status == "closed_tp"]
    assert len(trades) == 1
    t = trades[0]
    assert all(t.tp_filled)
    assert quantities_conserved(t)
    assert abs(t.remaining_quantity) <= 1e-9


def test_sl_after_partial_tp():
    sim = TradeSimulator(session_id="rp_test")
    sim.enable()
    candles = [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 100.5, 99.5, 100),
        _candle(2, 104, 106, 103, 105),
        _candle(3, 100, 101, 94, 95),
    ]
    for i, c in enumerate(candles):
        analysis = (
            _snap(replay_timestamp=candle_close_time(c, Timeframe.M5), event_index=0)
            if i == 0
            else None
        )
        sim.process_tick(
            analysis=analysis,
            execution_candle=c,
            series_by_tf={Timeframe.M5: candles[: i + 1]},
            clock=candle_close_time(c, Timeframe.M5),
            event_index=i,
        )
    t = next(iter(sim.trades.values()))
    assert t.lifecycle_status == "closed_sl"
    assert t.quantity_closed_tp > 0
    assert t.quantity_closed_sl > 0
    assert quantities_conserved(t)


def test_determinism_identical_replay():
    def run() -> list[tuple[str, str, float | None]]:
        sim = TradeSimulator(session_id="rp_det")
        sim.enable()
        candles = [
            _candle(0, 100, 101, 99, 100),
            _candle(1, 99.5, 100.5, 99, 100),
            _candle(2, 104, 106, 103, 105),
            _candle(3, 100, 101, 94, 95),
        ]
        for i, c in enumerate(candles):
            analysis = (
                _snap(
                    session_id="rp_det",
                    replay_timestamp=candle_close_time(c, Timeframe.M5),
                    event_index=0,
                )
                if i == 0
                else None
            )
            sim.process_tick(
                analysis=analysis,
                execution_candle=c,
                series_by_tf={Timeframe.M5: candles[: i + 1]},
                clock=candle_close_time(c, Timeframe.M5),
                event_index=i,
            )
        out = []
        for t in sorted(sim.trades.values(), key=lambda x: x.signal_key):
            for e in t.execution_events:
                out.append((e.event_type, t.lifecycle_status, e.price))
        return out

    assert run() == run()


def test_signal_key_stable():
    a = _snap()
    b = _snap()
    assert build_signal_key(a, "LONG") == build_signal_key(b, "LONG")


# ─── REST API ───


@pytest.fixture
def client():
    reset_replay_manager()
    yield TestClient(app)
    reset_replay_manager()


def test_simulation_api_enable_get_reset(client: TestClient, monkeypatch):
    from app.replay.manager import get_replay_manager
    from app.replay.session import ReplaySession
    from app.replay.timeline import build_event_timeline

    start = _ts(0)
    end = start + timedelta(hours=1)
    m5 = [
        _candle(i, 100.0, 101.0, 99.0, 100.0, market_type=MarketType.SPOT)
        for i in range(12)
    ]
    sess = ReplaySession(
        exchange=EX,
        symbol=SYM,
        market_type=MarketType.SPOT,
        start_time=start,
        end_time=end,
    )
    sess.series_by_tf = {
        Timeframe.M5: m5,
        Timeframe.M15: m5[::3] or m5[:1],
        Timeframe.H1: m5[:1],
        Timeframe.H4: m5[:1],
    }
    sess.event_times = build_event_timeline(
        sess.series_by_tf, start=start, end=end
    )
    assert sess.event_times, "expected synthetic event timeline"
    sess.status = "ready"
    get_replay_manager()._sessions[sess.session_id] = sess

    sid = sess.session_id

    async def fake_analysis(*, emit: bool = True):
        clock = sess.event_times[0] if sess.event_times else _ts(0)
        snap = _snap(
            session_id=sid,
            market_type=MarketType.SPOT,
            replay_timestamp=clock,
            decision="WAIT",
        )
        sess.current_analysis = snap
        sess._analysis_by_index[0] = snap
        if sess.simulator.enabled:
            await sess._run_simulation_unlocked(analysis=snap, emit=emit)
        return snap

    monkeypatch.setattr(sess, "_run_analysis_unlocked", fake_analysis)

    r = client.post(f"/api/v1/replay/sessions/{sid}/simulation/enable")
    assert r.status_code == 200
    data = r.json()
    assert data["simulation_enabled"] is True
    assert "HISTORICAL SIMULATION" in data["snapshot"]["disclaimer"]

    r2 = client.get(f"/api/v1/replay/sessions/{sid}/simulation")
    assert r2.status_code == 200
    assert r2.json()["simulation_enabled"] is True

    r3 = client.get(f"/api/v1/replay/sessions/{sid}/simulation/trades")
    assert r3.status_code == 200
    assert "trades" in r3.json()

    r4 = client.get(f"/api/v1/replay/sessions/{sid}/simulation/events")
    assert r4.status_code == 200

    r5 = client.post(f"/api/v1/replay/sessions/{sid}/simulation/reset")
    assert r5.status_code == 200

    r6 = client.post(f"/api/v1/replay/sessions/{sid}/simulation/disable")
    assert r6.status_code == 200
    assert r6.json()["simulation_enabled"] is False
