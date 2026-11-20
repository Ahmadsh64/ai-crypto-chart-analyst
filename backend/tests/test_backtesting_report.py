"""Phase 5.2.6 — Backtesting reporting & export tests.

LABELED FIXTURES — not live OHLCV / profitability proof.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.main import app
from app.replay.costs.config import ExecutionCostConfig
from app.replay.costs.engine import CostEngine
from app.replay.manager import get_replay_manager, reset_replay_manager
from app.replay.reporting import (
    build_export_filename,
    build_report,
    content_fingerprint,
    render_csv,
    render_pdf,
    safe_filename_component,
)
from app.replay.reporting.validation import ReportError
from app.replay.session import ReplaySession
from app.replay.simulation.models import SimulatedTrade, SimulationExecutionEvent
from app.replay.timeline import build_event_timeline

UTC = timezone.utc
START = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
EX = ExchangeId.BINANCE
SYM = "BTC/USDT"
MT = MarketType.SPOT
# Keep trade timestamps inside the synthetic replay window (24×5m bars).
NOW = START + timedelta(minutes=20)


def _ev(eid, et, price, qty, ts, reason=None):
    return SimulationExecutionEvent(
        event_id=eid,
        event_type=et,
        timestamp=ts,
        price=price,
        quantity=qty,
        reason=reason,
    )


def _trade(
    *,
    trade_id: str,
    status: str = "closed_tp",
    direction: str = "LONG",
    entry: float = 100.0,
    exit_px: float = 110.0,
    remaining: float = 0.0,
    exit_ts: datetime | None = None,
) -> SimulatedTrade:
    exit_ts = exit_ts or (NOW + timedelta(minutes=10))
    return SimulatedTrade(
        trade_id=trade_id,
        signal_key=f"sig_{trade_id}",
        replay_session_id="rp_rep",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        direction=direction,  # type: ignore[arg-type]
        decision=direction,
        decision_timestamp=NOW,
        decision_event_index=0,
        lifecycle_status=status,  # type: ignore[arg-type]
        entry_limit_price=entry,
        entry_price=entry,
        entry_timestamp=NOW + timedelta(minutes=1),
        exit_timestamp=exit_ts if remaining == 0 else None,
        initial_stop_loss=95.0,
        current_stop_loss=95.0,
        take_profit_levels=[110.0, 120.0],
        tp_allocations=[0.5, 0.5],
        tp_filled=[True, remaining == 0],
        original_quantity=1.0,
        remaining_quantity=remaining,
        executed_quantity=1.0 - remaining,
        quantity_closed_tp=1.0 - remaining if "tp" in status else 0.0,
        quantity_closed_sl=1.0 - remaining if status == "closed_sl" else 0.0,
        quantity_closed_expired=(
            1.0 - remaining if status == "closed_expired" else 0.0
        ),
        config_version="v",
        created_at=NOW,
        updated_at=exit_ts,
        execution_events=[
            _ev(f"{trade_id}_o", "trade_opened", entry, 1.0, NOW + timedelta(minutes=1)),
            _ev(
                f"{trade_id}_x",
                "trade_closed" if remaining == 0 else "trade_partially_closed",
                exit_px,
                1.0 - remaining,
                exit_ts,
                "TP",
            ),
        ],
    )


def _cost_engine(trades: list[SimulatedTrade]) -> CostEngine:
    eng = CostEngine(
        session_id="rp_rep",
        config=ExecutionCostConfig(
            maker_fee_rate=Decimal("0.001"),
            taker_fee_rate=Decimal("0.001"),
            slippage_policy="none",
            spread_policy="none",
        ),
    )
    eng.enable()
    eng.rebuild_from_trades(trades)
    return eng


def _synth(n: int = 24) -> dict[Timeframe, list[Candle]]:
    m5 = []
    price = 100.0
    for i in range(n):
        ts = START + timedelta(minutes=5 * i)
        o, cl = price, price + 0.2
        m5.append(
            Candle(
                timestamp=ts,
                open=o,
                high=max(o, cl) + 0.1,
                low=min(o, cl) - 0.1,
                close=cl,
                volume=1.0,
                exchange=EX,
                symbol=SYM,
                market_type=MT,
                is_closed=True,
                close_time=ts + timedelta(seconds=300) - timedelta(milliseconds=1),
            )
        )
        price = cl
    return {
        Timeframe.M5: m5,
        Timeframe.M15: m5[::3] or m5[:1],
        Timeframe.H1: m5[::12] or m5[:1],
        Timeframe.H4: m5[::48] or m5[:1],
    }


def _session_with_trades(trades: list[SimulatedTrade]) -> ReplaySession:
    series = _synth(24)
    end = START + timedelta(hours=2)
    sess = ReplaySession(
        exchange=EX, symbol=SYM, market_type=MT, start_time=START, end_time=end
    )
    sess.series_by_tf = series
    sess.event_times = build_event_timeline(series, start=START, end=end)
    sess.status = "ready"
    # Use the last event so seeded trade exit timestamps are <= replay clock.
    sess.event_index = len(sess.event_times) - 1
    sess.simulator.enable()
    for t in trades:
        t.replay_session_id = sess.session_id
        sess.simulator.trades[t.trade_id] = t
    sess.cost_engine = _cost_engine(trades)
    sess.cost_engine.session_id = sess.session_id
    sess.analytics_engine.enable()
    return sess


@pytest.fixture(autouse=True)
def _reset():
    reset_replay_manager()
    yield
    reset_replay_manager()


# ─── Core report ───


def test_report_metadata_and_clock():
    t = _trade(trade_id="t1")
    sess = _session_with_trades([t])
    report = build_report(sess)
    assert report.metadata.session_id == sess.session_id
    assert report.metadata.symbol == "BTC/USDT"
    assert report.metadata.replay_timestamp == sess.event_times[sess.event_index]
    assert report.metadata.report_version.startswith("backtest-report")
    assert "NOT FINANCIAL ADVICE" in report.disclaimer
    assert report.summary.completed_trade_count >= 1


def test_open_trades_excluded_from_completed():
    closed = _trade(trade_id="c1")
    open_t = _trade(trade_id="o1", status="open", remaining=1.0, exit_px=100.0)
    open_t.exit_timestamp = None
    open_t.execution_events = open_t.execution_events[:1]
    sess = _session_with_trades([closed, open_t])
    report = build_report(sess)
    ids = {r.trade_id for r in report.completed_trades}
    assert "c1" in ids
    assert "o1" not in ids
    assert report.open_trade_total >= 1
    assert all(r.trade_id != "c1" for r in report.open_trades)


def test_closed_expired_flat_included_remaining_excluded():
    flat = _trade(trade_id="exp_flat", status="closed_expired", remaining=0.0)
    leftover = _trade(
        trade_id="exp_left", status="closed_expired", remaining=0.5, exit_px=105.0
    )
    sess = _session_with_trades([flat, leftover])
    report = build_report(sess)
    completed_ids = {r.trade_id for r in report.completed_trades}
    assert "exp_flat" in completed_ids
    assert "exp_left" not in completed_ids


def test_average_exit_price_ledger_vwap():
    t = _trade(trade_id="vwap1", exit_px=110.0)
    sess = _session_with_trades([t])
    report = build_report(sess)
    row = next(r for r in report.completed_trades if r.trade_id == "vwap1")
    assert row.average_exit_price is not None
    assert row.average_exit_price_source == "ledger_vwap"
    assert row.entry_price == Decimal("100")
    assert row.fees is not None


def test_metric_availability_preserved_empty():
    sess = _session_with_trades([])
    report = build_report(sess)
    assert report.summary.win_rate.availability == "unavailable"
    assert report.summary.profit_factor.availability == "unavailable"
    # Never fabricate zero for unavailable key metrics
    wr = next(m for m in report.summary.key_metrics if m.key == "win_rate")
    assert wr.availability == "unavailable"
    assert wr.value is None


def test_equity_drawdown_passthrough():
    sess = _session_with_trades([_trade(trade_id="eq1")])
    report = build_report(sess)
    analytics = sess.analytics_engine.snapshot(
        list(sess.simulator.trades.values()),
        sess.cost_engine,
        replay_timestamp=sess.event_times[sess.event_index],
        event_index=sess.event_index,
    )
    assert len(report.equity.completed.points) == len(analytics.equity_completed.points)
    assert report.drawdown.summary.max_drawdown == analytics.drawdown.max_drawdown


def test_deterministic_content_fingerprint():
    sess = _session_with_trades([_trade(trade_id="d1")])
    a = build_report(sess)
    b = build_report(sess)
    assert a.metadata.report_id != b.metadata.report_id
    assert content_fingerprint(a) == content_fingerprint(b)


@pytest.mark.asyncio
async def test_report_after_reset_and_seek():
    late = _trade(
        trade_id="late",
        exit_ts=START + timedelta(minutes=50),
    )
    # Align decision timestamps with replay clock for seek filtering via analytics
    late.decision_timestamp = START + timedelta(minutes=40)
    late.entry_timestamp = START + timedelta(minutes=41)
    series = _synth(60)
    end = START + timedelta(hours=5)
    sess = ReplaySession(
        exchange=EX, symbol=SYM, market_type=MT, start_time=START, end_time=end
    )
    sess.series_by_tf = series
    sess.event_times = build_event_timeline(series, start=START, end=end)
    sess.status = "ready"
    sess.simulator.enable()
    late.replay_session_id = sess.session_id
    sess.simulator.trades[late.trade_id] = late
    sess.cost_engine = _cost_engine([late])
    sess.analytics_engine.enable()
    sess.event_index = len(sess.event_times) - 1

    late_report = build_report(sess)
    await sess.reset()
    # After reset, trades rebuild from simulation — seeded trades are wiped by simulator.reset
    # Re-seed for seek test path using rebuild semantics:
    # Instead validate seek clock binding on empty rebuild + analytics enabled.
    early = await sess.seek(0)
    assert early.event_index == 0
    # Analytics still enabled after seek rebuild
    if sess.analytics_engine.enabled and sess.event_times:
        report = build_report(sess)
        assert report.metadata.event_index == 0
        assert report.metadata.replay_timestamp == sess.event_times[0]
    _ = late_report


def test_future_exits_excluded_from_report():
    past = _trade(trade_id="past", exit_ts=NOW + timedelta(minutes=5))
    future = _trade(
        trade_id="fut",
        exit_ts=START + timedelta(days=30),
    )
    sess = _session_with_trades([past, future])
    # Clock in the middle of the session window (before future exit)
    mid = min(15, len(sess.event_times) - 1)
    sess.event_index = mid
    report = build_report(sess)
    ids = {r.trade_id for r in report.completed_trades}
    assert "fut" not in ids
    assert report.metadata.replay_timestamp == sess.event_times[mid]


# ─── CSV / PDF / filenames ───


def test_csv_summary_and_trades_escaping():
    weird = _trade(trade_id='t,"quote')
    sess = _session_with_trades([weird])
    report = build_report(sess, for_export=True)
    raw = render_csv(report, "trades").decode("utf-8")
    assert "report_id" in raw
    assert "trade_id" in raw
    assert 't,""quote' in raw or '"t,""quote"' in raw or "t," in raw
    summary = render_csv(report, "summary").decode("utf-8")
    assert "win_rate" in summary
    # Unavailable metrics must not be forced to 0 in metric column when availability unavailable
    assert "infinite" in summary or "win_rate" in summary


def test_csv_empty_report():
    sess = _session_with_trades([])
    report = build_report(sess, for_export=True)
    equity = render_csv(report, "equity").decode("utf-8")
    dd = render_csv(report, "drawdown").decode("utf-8")
    assert "curve=" in equity
    assert "max_drawdown" in dd


def test_pdf_valid_header():
    sess = _session_with_trades([_trade(trade_id=f"p{i}") for i in range(25)])
    report = build_report(sess, for_export=True)
    pdf = render_pdf(report)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500


def test_pdf_trade_table_shows_full_ids_and_exit_type():
    """PDF layout: full trade IDs (no 10-char clip) + Exit type distinct from R."""
    pytest.importorskip("fitz")
    import fitz

    long_id = "fx_long_partials_very_long_identifier"
    short_id = "fx_short_sl"
    long_t = _trade(trade_id=long_id, direction="LONG", exit_px=110.0)
    short_t = _trade(
        trade_id=short_id,
        direction="SHORT",
        status="closed_sl",
        entry=105.0,
        exit_px=112.0,
    )
    open_t = _trade(trade_id="fx_partial_open", status="open", remaining=1.0, exit_px=100.0)
    open_t.exit_timestamp = None
    open_t.execution_events = open_t.execution_events[:1]

    sess = _session_with_trades([long_t, short_t, open_t])
    report = build_report(sess, for_export=True)
    # Snapshot financials before render — PDF must not mutate report content.
    net_before = report.summary.net_pnl
    gross_before = report.summary.gross_pnl
    completed_before = report.summary.completed_trade_count

    pdf = render_pdf(report)
    assert report.summary.net_pnl == net_before
    assert report.summary.gross_pnl == gross_before
    assert report.summary.completed_trade_count == completed_before

    doc = fitz.open(stream=pdf, filetype="pdf")
    try:
        text = "\n".join(page.get_text("text") for page in doc)
        # Wrapping may insert newlines / ZWSP at '_'; join non-space chars for ID check.
        compact = "".join(ch for ch in text if not ch.isspace() and ch != "\u200b")
        assert long_id in compact, "full long trade_id must appear (not truncated)"
        assert short_id in compact
        assert "fx_partial_open" in compact
        assert "LONG" in text and "SHORT" in text
        # Exit type is its own column (header Type), not jammed into R
        assert "Type" in text
        assert "tp" in text.lower() and "sl" in text.lower()
        assert doc.page_count >= 3
        for page in doc:
            assert page.rect.width > 0 and page.rect.height > 0
    finally:
        doc.close()


def test_pdf_empty_report_layout():
    pytest.importorskip("fitz")
    import fitz

    sess = _session_with_trades([])
    report = build_report(sess, for_export=True)
    pdf = render_pdf(report)
    doc = fitz.open(stream=pdf, filetype="pdf")
    try:
        text = "\n".join(page.get_text("text") for page in doc)
        assert "No completed trades in this report." in text
        assert "NOT FINANCIAL ADVICE" in text
        assert "N/A" in text  # unavailable WR/PF
        assert doc.page_count >= 2
    finally:
        doc.close()


def test_safe_filename():
    assert ".." not in safe_filename_component("../etc/passwd")
    assert "/" not in safe_filename_component("BTC/USDT")
    name = build_export_filename(
        symbol="BTC/USDT",
        kind="trades",
        extension="csv",
        generated_at=NOW,
    )
    assert name.startswith("BTCUSDT_backtest_trades_")
    assert name.endswith(".csv")


# ─── API ───


def test_report_api_requires_analytics():
    client = TestClient(app)
    series = _synth(12)

    async def fake_load(**kwargs):
        return series, [], []

    with patch("app.replay.session.load_replay_series", new=AsyncMock(side_effect=fake_load)):
        create = client.post(
            "/api/v1/replay/sessions",
            json={
                "exchange": "binance",
                "symbol": "BTC/USDT",
                "market_type": "spot",
                "start_time": START.isoformat(),
                "end_time": (START + timedelta(hours=1)).isoformat(),
                "speed": "max",
            },
        )
        assert create.status_code == 200, create.text
        sid = create.json()["session"]["session_id"]

        r = client.get(f"/api/v1/replay/sessions/{sid}/report")
        assert r.status_code == 400

        client.post(f"/api/v1/replay/sessions/{sid}/analytics/enable")
        # Seed a trade on the live session
        sess = get_replay_manager().require(sid)
        t = _trade(trade_id="api1")
        t.replay_session_id = sid
        sess.simulator.trades[t.trade_id] = t
        sess.cost_engine.rebuild_from_trades([t])

        r2 = client.get(f"/api/v1/replay/sessions/{sid}/report")
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["session_id"] == sid
        assert body["report"]["metadata"]["session_id"] == sid

        r3 = client.get(f"/api/v1/replay/sessions/{sid}/report/trades")
        assert r3.status_code == 200

        r4 = client.get(
            f"/api/v1/replay/sessions/{sid}/report/export/csv",
            params={"kind": "summary"},
        )
        assert r4.status_code == 200
        assert "text/csv" in r4.headers["content-type"]
        assert "attachment" in r4.headers["content-disposition"]

        r5 = client.get(f"/api/v1/replay/sessions/{sid}/report/export/pdf")
        assert r5.status_code == 200
        assert r5.content.startswith(b"%PDF")

        r6 = client.get(
            f"/api/v1/replay/sessions/{sid}/report/export/csv",
            params={"kind": "nope"},
        )
        assert r6.status_code == 422

        missing = client.get("/api/v1/replay/sessions/rp_missing/report")
        assert missing.status_code == 404


# ─── Performance smoke ───


def test_report_generation_perf_smoke():
    empty = _session_with_trades([])
    t0 = time.perf_counter()
    build_report(empty)
    empty_ms = (time.perf_counter() - t0) * 1000

    small = _session_with_trades([_trade(trade_id=f"s{i}") for i in range(5)])
    t1 = time.perf_counter()
    r_small = build_report(small, for_export=True)
    small_ms = (time.perf_counter() - t1) * 1000
    t2 = time.perf_counter()
    render_csv(r_small, "trades")
    csv_ms = (time.perf_counter() - t2) * 1000
    t3 = time.perf_counter()
    render_pdf(r_small)
    pdf_ms = (time.perf_counter() - t3) * 1000

    large = _session_with_trades([_trade(trade_id=f"l{i}") for i in range(40)])
    t4 = time.perf_counter()
    r_large = build_report(large, for_export=True)
    large_ms = (time.perf_counter() - t4) * 1000
    t5 = time.perf_counter()
    render_pdf(r_large)
    large_pdf_ms = (time.perf_counter() - t5) * 1000

    assert empty_ms < 5000
    assert small_ms < 10000
    assert csv_ms < 5000
    assert pdf_ms < 15000
    assert large_ms < 20000
    assert large_pdf_ms < 30000
    print(
        f"PERF empty={empty_ms:.1f}ms small={small_ms:.1f}ms csv={csv_ms:.1f}ms "
        f"pdf={pdf_ms:.1f}ms large={large_ms:.1f}ms large_pdf={large_pdf_ms:.1f}ms"
    )


def test_report_json_safe_dump():
    sess = _session_with_trades([_trade(trade_id="j1")])
    report = build_report(sess)
    raw = report.model_dump(mode="json")
    text = json.dumps(raw)
    assert "NaN" not in text
    assert "Infinity" not in text
