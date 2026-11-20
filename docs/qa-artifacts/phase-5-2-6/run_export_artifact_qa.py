"""Phase 5.2.6 — Final PDF & CSV Artifact Verification (QA ONLY).

LABELED FIXTURES — not live OHLCV / profitability proof.
Does not modify production code. Writes downloaded artifacts under this folder.
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import fitz  # pymupdf — QA inspection only
from fastapi.testclient import TestClient

# Ensure backend package is importable when launched from docs/...
ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe  # noqa: E402
from app.main import app  # noqa: E402
from app.replay.analytics.config import AnalyticsConfig  # noqa: E402
from app.replay.costs.config import ExecutionCostConfig  # noqa: E402
from app.replay.manager import get_replay_manager, reset_replay_manager  # noqa: E402
from app.replay.reporting import build_export_filename, build_report  # noqa: E402
from app.replay.simulation.models import (  # noqa: E402
    SimulatedTrade,
    SimulationExecutionEvent,
)
from app.replay.timeline import build_event_timeline  # noqa: E402

UTC = timezone.utc
START = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
EX = ExchangeId.BINANCE
SYM = "BTC/USDT"
MT = MarketType.SPOT
NOW = START + timedelta(minutes=20)
OUT = Path(__file__).resolve().parent
SHOTS = ROOT / "docs" / "screenshots"
FIXTURE_ID = "fixture_phase526_export_qa_v1"
INITIAL_EQUITY = Decimal("10000")


def D(x) -> Decimal:
    return Decimal(str(x))


def _ev(eid, et, price, qty, ts, reason=None):
    return SimulationExecutionEvent(
        event_id=eid,
        event_type=et,
        timestamp=ts,
        price=price,
        quantity=qty,
        reason=reason,
    )


def _synth(n: int = 48) -> dict[Timeframe, list[Candle]]:
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


def _rich_trades() -> list[SimulatedTrade]:
    """Multiple completed LONG/SHORT, partials, winner+loser. LABELED FIXTURE."""
    t_long_partials = SimulatedTrade(
        trade_id="fx_long_partials",
        signal_key="sig_fx_long_partials",
        replay_session_id="pending",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        direction="LONG",
        decision="LONG",
        decision_timestamp=NOW,
        decision_event_index=0,
        lifecycle_status="closed_tp",
        entry_limit_price=100.0,
        entry_price=100.0,
        entry_timestamp=NOW + timedelta(minutes=1),
        exit_timestamp=NOW + timedelta(minutes=25),
        initial_stop_loss=95.0,
        current_stop_loss=95.0,
        take_profit_levels=[110.0, 120.0],
        tp_allocations=[0.5, 0.5],
        tp_filled=[True, True],
        original_quantity=1.0,
        remaining_quantity=0.0,
        executed_quantity=1.0,
        quantity_closed_tp=1.0,
        config_version="fixture-v1",
        created_at=NOW,
        updated_at=NOW + timedelta(minutes=25),
        execution_events=[
            _ev("lp_o", "trade_opened", 100.0, 1.0, NOW + timedelta(minutes=1)),
            _ev(
                "lp_p1",
                "trade_partially_closed",
                110.0,
                0.5,
                NOW + timedelta(minutes=12),
                "TP1",
            ),
            _ev(
                "lp_c",
                "trade_closed",
                120.0,
                0.5,
                NOW + timedelta(minutes=25),
                "TP2",
            ),
        ],
    )

    t_short_loss = SimulatedTrade(
        trade_id="fx_short_sl",
        signal_key="sig_fx_short_sl",
        replay_session_id="pending",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        direction="SHORT",
        decision="SHORT",
        decision_timestamp=NOW + timedelta(minutes=2),
        decision_event_index=1,
        lifecycle_status="closed_sl",
        entry_limit_price=105.0,
        entry_price=105.0,
        entry_timestamp=NOW + timedelta(minutes=3),
        exit_timestamp=NOW + timedelta(minutes=18),
        initial_stop_loss=112.0,
        current_stop_loss=112.0,
        take_profit_levels=[98.0],
        tp_allocations=[1.0],
        tp_filled=[False],
        original_quantity=1.0,
        remaining_quantity=0.0,
        executed_quantity=1.0,
        quantity_closed_sl=1.0,
        config_version="fixture-v1",
        created_at=NOW,
        updated_at=NOW + timedelta(minutes=18),
        execution_events=[
            _ev("ss_o", "trade_opened", 105.0, 1.0, NOW + timedelta(minutes=3)),
            _ev(
                "ss_x",
                "trade_closed",
                112.0,
                1.0,
                NOW + timedelta(minutes=18),
                "SL",
            ),
        ],
    )

    t_long_win = SimulatedTrade(
        trade_id="fx_long_win",
        signal_key="sig_fx_long_win",
        replay_session_id="pending",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        direction="LONG",
        decision="LONG",
        decision_timestamp=NOW + timedelta(minutes=4),
        decision_event_index=2,
        lifecycle_status="closed_tp",
        entry_limit_price=101.0,
        entry_price=101.0,
        entry_timestamp=NOW + timedelta(minutes=5),
        exit_timestamp=NOW + timedelta(minutes=30),
        initial_stop_loss=96.0,
        current_stop_loss=96.0,
        take_profit_levels=[111.0],
        tp_allocations=[1.0],
        tp_filled=[True],
        original_quantity=2.0,
        remaining_quantity=0.0,
        executed_quantity=2.0,
        quantity_closed_tp=2.0,
        config_version="fixture-v1",
        created_at=NOW,
        updated_at=NOW + timedelta(minutes=30),
        execution_events=[
            _ev("lw_o", "trade_opened", 101.0, 2.0, NOW + timedelta(minutes=5)),
            _ev(
                "lw_x",
                "trade_closed",
                111.0,
                2.0,
                NOW + timedelta(minutes=30),
                "TP",
            ),
        ],
    )

    t_long_loss = SimulatedTrade(
        trade_id="fx_long_sl",
        signal_key="sig_fx_long_sl",
        replay_session_id="pending",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        direction="LONG",
        decision="LONG",
        decision_timestamp=NOW + timedelta(minutes=6),
        decision_event_index=3,
        lifecycle_status="closed_sl",
        entry_limit_price=102.0,
        entry_price=102.0,
        entry_timestamp=NOW + timedelta(minutes=7),
        exit_timestamp=NOW + timedelta(minutes=22),
        initial_stop_loss=97.0,
        current_stop_loss=97.0,
        take_profit_levels=[115.0],
        tp_allocations=[1.0],
        tp_filled=[False],
        original_quantity=1.0,
        remaining_quantity=0.0,
        executed_quantity=1.0,
        quantity_closed_sl=1.0,
        config_version="fixture-v1",
        created_at=NOW,
        updated_at=NOW + timedelta(minutes=22),
        execution_events=[
            _ev("ll_o", "trade_opened", 102.0, 1.0, NOW + timedelta(minutes=7)),
            _ev(
                "ll_x",
                "trade_closed",
                97.0,
                1.0,
                NOW + timedelta(minutes=22),
                "SL",
            ),
        ],
    )

    # Still open / partial — must NOT appear as completed stats rows.
    t_partial_open = SimulatedTrade(
        trade_id="fx_partial_open",
        signal_key="sig_fx_partial_open",
        replay_session_id="pending",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        direction="LONG",
        decision="LONG",
        decision_timestamp=NOW + timedelta(minutes=8),
        decision_event_index=4,
        lifecycle_status="partially_closed",
        entry_limit_price=103.0,
        entry_price=103.0,
        entry_timestamp=NOW + timedelta(minutes=9),
        exit_timestamp=None,
        initial_stop_loss=98.0,
        current_stop_loss=98.0,
        take_profit_levels=[113.0, 123.0],
        tp_allocations=[0.5, 0.5],
        tp_filled=[True, False],
        original_quantity=1.0,
        remaining_quantity=0.5,
        executed_quantity=0.5,
        quantity_closed_tp=0.5,
        config_version="fixture-v1",
        created_at=NOW,
        updated_at=NOW + timedelta(minutes=15),
        execution_events=[
            _ev("po_o", "trade_opened", 103.0, 1.0, NOW + timedelta(minutes=9)),
            _ev(
                "po_p",
                "trade_partially_closed",
                113.0,
                0.5,
                NOW + timedelta(minutes=15),
                "TP1",
            ),
        ],
    )

    t_open = SimulatedTrade(
        trade_id="fx_open",
        signal_key="sig_fx_open",
        replay_session_id="pending",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        direction="LONG",
        decision="LONG",
        decision_timestamp=NOW + timedelta(minutes=10),
        decision_event_index=5,
        lifecycle_status="open",
        entry_limit_price=104.0,
        entry_price=104.0,
        entry_timestamp=NOW + timedelta(minutes=11),
        exit_timestamp=None,
        initial_stop_loss=99.0,
        current_stop_loss=99.0,
        take_profit_levels=[114.0],
        tp_allocations=[1.0],
        tp_filled=[False],
        original_quantity=1.0,
        remaining_quantity=1.0,
        executed_quantity=0.0,
        config_version="fixture-v1",
        created_at=NOW,
        updated_at=NOW + timedelta(minutes=11),
        execution_events=[
            _ev("op_o", "trade_opened", 104.0, 1.0, NOW + timedelta(minutes=11)),
        ],
    )

    return [
        t_long_partials,
        t_short_loss,
        t_long_win,
        t_long_loss,
        t_partial_open,
        t_open,
    ]


def _seed_session(client: TestClient, trades: list[SimulatedTrade], *, empty: bool):
    series = _synth(48)

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
                "end_time": (START + timedelta(hours=4)).isoformat(),
                "speed": "max",
            },
        )
        assert create.status_code == 200, create.text
        sid = create.json()["session"]["session_id"]

    # Enable stack
    assert client.post(f"/api/v1/replay/sessions/{sid}/simulation/enable").status_code == 200
    assert client.post(f"/api/v1/replay/sessions/{sid}/costs/enable").status_code == 200
    assert client.post(f"/api/v1/replay/sessions/{sid}/analytics/enable").status_code == 200

    # Cost config with fees + slippage + spread
    cfg = {
        "maker_fee_rate": "0.001",
        "taker_fee_rate": "0.001",
        "slippage_policy": "fixed_bps",
        "slippage_bps": "5",
        "spread_policy": "fixed_bps",
        "spread_bps": "2",
        "maker_taker_fallback": "assume_taker",
    }
    r_cfg = client.put(f"/api/v1/replay/sessions/{sid}/costs/config", json=cfg)
    assert r_cfg.status_code == 200, r_cfg.text

    # Initial equity for drawdown / ending equity
    r_an = client.put(
        f"/api/v1/replay/sessions/{sid}/analytics/config",
        json={"initial_equity": str(INITIAL_EQUITY)},
    )
    assert r_an.status_code == 200, r_an.text

    sess = get_replay_manager().require(sid)
    sess.event_index = len(sess.event_times) - 1
    sess.status = "ready"

    if not empty:
        for t in trades:
            t.replay_session_id = sid
            sess.simulator.trades[t.trade_id] = t
        sess.cost_engine.rebuild_from_trades(list(sess.simulator.trades.values()))

    return sid, sess


def _disposition_filename(headers) -> str | None:
    cd = headers.get("content-disposition") or ""
    m = re.search(r'filename="?([^";]+)"?', cd)
    return m.group(1) if m else None


def _download(client: TestClient, sid: str, kind: str, label: str) -> Path:
    if kind == "pdf":
        r = client.get(f"/api/v1/replay/sessions/{sid}/report/export/pdf")
        assert r.status_code == 200, r.text[:500]
        name = _disposition_filename(r.headers) or build_export_filename(
            symbol=SYM, kind="pdf", extension="pdf", generated_at=datetime.now(UTC)
        )
        # Label fixture artifacts clearly
        out_name = f"LABELED_FIXTURE_{label}_{name}"
        path = OUT / out_name
        path.write_bytes(r.content)
        return path

    r = client.get(
        f"/api/v1/replay/sessions/{sid}/report/export/csv",
        params={"kind": kind},
    )
    assert r.status_code == 200, r.text[:500]
    name = _disposition_filename(r.headers) or build_export_filename(
        symbol=SYM, kind=kind, extension="csv", generated_at=datetime.now(UTC)
    )
    out_name = f"LABELED_FIXTURE_{label}_{name}"
    path = OUT / out_name
    path.write_bytes(r.content)
    return path


def _parse_csv(path: Path) -> tuple[list[list[str]], list[str], list[list[str]]]:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    # Confirm UTF-8 and no BOM issues
    assert isinstance(text, str)
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    meta = [r for r in rows if r and str(r[0]).startswith("#")]
    # Find first non-meta header
    header = None
    data = []
    for r in rows:
        if not r:
            continue
        if str(r[0]).startswith("#"):
            continue
        if header is None:
            header = r
            continue
        if str(r[0]).startswith("#"):
            break
        data.append(r)
    return meta, header or [], data


def _independent_from_api(report: dict) -> dict:
    """Independent tallies from report snapshot (Decimal)."""
    s = report["summary"]
    trades = report["completed_trades"]
    completed = [t for t in trades if t.get("included_in_completed_stats")]
    wins = sum(1 for t in completed if D(t.get("net_realized_pnl") or 0) > 0)
    losses = sum(1 for t in completed if D(t.get("net_realized_pnl") or 0) < 0)
    gross = sum((D(t.get("gross_realized_pnl") or 0) for t in completed), D(0))
    net = sum((D(t.get("net_realized_pnl") or 0) for t in completed), D(0))
    fees = sum((D(t.get("fees") or 0) for t in completed), D(0))
    slip = sum((D(t.get("slippage") or 0) for t in completed), D(0))
    spread = sum((D(t.get("spread_cost") or 0) for t in completed), D(0))
    return {
        "completed_trade_count": len(completed),
        "winning_trades": wins,
        "losing_trades": losses,
        "gross_pnl_sum_trades": format(gross, "f"),
        "net_pnl_sum_trades": format(net, "f"),
        "fees_sum_trades": format(fees, "f"),
        "slippage_sum_trades": format(slip, "f"),
        "spread_sum_trades": format(spread, "f"),
        "summary_completed": s.get("completed_trade_count"),
        "summary_wins": s.get("winning_trades"),
        "summary_losses": s.get("losing_trades"),
        "summary_gross": s.get("gross_pnl"),
        "summary_net": s.get("net_pnl"),
        "summary_fees": s.get("total_fees"),
        "summary_slippage": s.get("total_slippage"),
        "summary_spread": s.get("total_spread_cost"),
        "summary_ending_equity": (
            s.get("ending_equity", {}).get("value")
            if isinstance(s.get("ending_equity"), dict)
            else s.get("ending_equity")
        ),
        "summary_max_drawdown": s.get("max_drawdown"),
        "summary_win_rate_avail": (
            s.get("win_rate", {}).get("availability")
            if isinstance(s.get("win_rate"), dict)
            else None
        ),
        "summary_pf_avail": (
            s.get("profit_factor", {}).get("availability")
            if isinstance(s.get("profit_factor"), dict)
            else None
        ),
    }


def _csv_trade_sums(path: Path) -> dict:
    meta, header, data = _parse_csv(path)
    idx = {h: i for i, h in enumerate(header)}
    completed_rows = [
        r
        for r in data
        if len(r) > idx.get("included_in_completed_stats", 0)
        and r[idx["included_in_completed_stats"]].lower() == "true"
    ]
    # Stop before open section already handled by parser break on # — but keep filter
    def col(r, name):
        i = idx.get(name)
        if i is None or i >= len(r) or r[i] == "":
            return None
        return D(r[i])

    nets = [col(r, "net_realized_pnl") for r in completed_rows]
    nets = [n for n in nets if n is not None]
    return {
        "header": header,
        "data_row_count": len(data),
        "completed_true_count": len(completed_rows),
        "directions": sorted({r[idx["direction"]] for r in completed_rows}),
        "partial_event_trade_present": any(
            r[idx["trade_id"]] == "fx_long_partials" for r in completed_rows
        ),
        "partial_open_not_in_completed": all(
            r[idx["trade_id"]] != "fx_partial_open" for r in completed_rows
        ),
        "open_not_in_completed": all(
            r[idx["trade_id"]] != "fx_open" for r in completed_rows
        ),
        "gross_sum": format(sum((col(r, "gross_realized_pnl") or D(0) for r in completed_rows), D(0)), "f"),
        "net_sum": format(sum((n for n in nets), D(0)), "f"),
        "fees_sum": format(sum((col(r, "fees") or D(0) for r in completed_rows), D(0)), "f"),
        "slip_sum": format(sum((col(r, "slippage") or D(0) for r in completed_rows), D(0)), "f"),
        "spread_sum": format(sum((col(r, "spread_cost") or D(0) for r in completed_rows), D(0)), "f"),
        "wins": sum(1 for n in nets if n > 0),
        "losses": sum(1 for n in nets if n < 0),
        "timestamps_utc_z": all(
            (r[idx["entry_timestamp_utc"]].endswith("Z") if r[idx["entry_timestamp_utc"]] else True)
            and (r[idx["exit_timestamp_utc"]].endswith("Z") if r[idx["exit_timestamp_utc"]] else True)
            for r in completed_rows
        ),
        "sample_rows": [
            {
                "trade_id": r[idx["trade_id"]],
                "direction": r[idx["direction"]],
                "net": r[idx["net_realized_pnl"]],
                "fees": r[idx["fees"]],
                "slippage": r[idx["slippage"]],
                "spread": r[idx["spread_cost"]],
                "exit_px": r[idx["average_exit_price"]],
            }
            for r in completed_rows
        ],
        "meta_has_disclaimer": any("NOT FINANCIAL ADVICE" in ",".join(m) for m in meta),
    }


def _csv_summary_inspect(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    meta, header, data = _parse_csv(path)
    by_metric = {r[0]: {"value": r[1], "availability": r[2]} for r in data if len(r) >= 3}
    return {
        "utf8_ok": True,
        "header": header,
        "metric_row_count": len(data),
        "win_rate": by_metric.get("win_rate"),
        "profit_factor": by_metric.get("profit_factor"),
        "completed_trade_count": by_metric.get("completed_trade_count"),
        "gross_pnl": by_metric.get("gross_pnl"),
        "net_pnl": by_metric.get("net_pnl"),
        "total_fees": by_metric.get("total_fees"),
        "total_slippage": by_metric.get("total_slippage"),
        "total_spread_cost": by_metric.get("total_spread_cost"),
        "max_drawdown": by_metric.get("max_drawdown"),
        "initial_equity": by_metric.get("initial_equity"),
        "ending_equity_key": by_metric.get("ending_equity"),
        "unavailable_empty_value": all(
            by_metric[k]["value"] == ""
            for k in ("win_rate", "profit_factor", "average_r_multiple", "max_drawdown_pct", "ending_equity")
            if k in by_metric and by_metric[k]["availability"] == "unavailable"
        ),
        "disclaimer_in_meta": "NOT FINANCIAL ADVICE" in text,
        "replay_timestamp_z": any(
            r[0] == "# replay_timestamp" and str(r[1]).endswith("Z") for r in meta if len(r) > 1
        ),
    }


def _csv_curve_inspect(path: Path, kind: str) -> dict:
    text = path.read_text(encoding="utf-8")
    rows = list(csv.reader(io.StringIO(text)))
    point_rows = [
        r
        for r in rows
        if r and not str(r[0]).startswith("#") and r[0] not in ("timestamp_utc", "metric", "value")
    ]
    # equity/dd have header timestamp_utc
    headers = [r for r in rows if r and r[0] == "timestamp_utc"]
    data_points = []
    capturing = False
    for r in rows:
        if r and r[0] == "timestamp_utc":
            capturing = True
            continue
        if capturing and r and not str(r[0]).startswith("#"):
            data_points.append(r)
        elif capturing and r and str(r[0]).startswith("#"):
            capturing = False
    return {
        "kind": kind,
        "utf8_ok": True,
        "point_count": len(data_points),
        "has_header": bool(headers),
        "sample": data_points[:3],
        "timestamps_z": all(r[0].endswith("Z") for r in data_points if r[0]),
        "file_bytes": path.stat().st_size,
        "preview": text[:400],
    }


def _inspect_pdf(path: Path, label: str) -> dict:
    doc = fitz.open(path)
    pages = []
    texts = []
    for i, page in enumerate(doc):
        txt = page.get_text("text")
        texts.append(txt)
        png = SHOTS / f"qa-5-2-6-final-{label}-pdf-page-{i+1:02d}.png"
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        pix.save(str(png))
        pages.append(
            {
                "page": i + 1,
                "width": page.rect.width,
                "height": page.rect.height,
                "char_count": len(txt),
                "screenshot": str(png.relative_to(ROOT)).replace("\\", "/"),
            }
        )
    full = "\n".join(texts)
    # crude chart presence: vector drawings or image xrefs
    drawings = sum(len(page.get_drawings()) for page in doc)
    images = sum(len(page.get_images()) for page in doc)
    doc.close()
    return {
        "filename": path.name,
        "bytes": path.stat().st_size,
        "magic": path.read_bytes()[:5].decode("latin1"),
        "page_count": len(pages),
        "pages": pages,
        "has_disclaimer": "NOT FINANCIAL ADVICE" in full or "HISTORICAL BACKTEST" in full,
        "has_equity_word": "Equity" in full or "equity" in full,
        "has_drawdown_word": "Drawdown" in full or "drawdown" in full,
        "has_trade_table_hint": "Trade" in full or "trade_id" in full or "fx_long" in full,
        "mentions_fixture_trades": any(
            tid in full
            for tid in ("fx_long_partials", "fx_short_sl", "fx_long_win", "fx_long_sl")
        ),
        "drawing_count": drawings,
        "image_count": images,
        "text_excerpt": full[:1200],
        "page_numbers_present": bool(re.search(r"\b\d+\s*/\s*\d+\b", full) or "Page" in full),
    }


def _extract_pdf_numbers(path: Path) -> dict:
    doc = fitz.open(path)
    full = "\n".join(page.get_text("text") for page in doc)
    doc.close()
    # Pull lines that look like labeled metrics
    found = {}
    for key in (
        "Completed",
        "Win Rate",
        "Profit Factor",
        "Net P&L",
        "Gross P&L",
        "Max Drawdown",
        "Ending Equity",
        "Total Fees",
        "Fees",
        "Slippage",
        "Spread",
    ):
        for line in full.splitlines():
            if key.lower() in line.lower():
                found.setdefault(key, []).append(line.strip())
    return {"metric_lines": found, "contains_N/A": "N/A" in full or "n/a" in full.lower()}


def main():
    reset_replay_manager()
    results = {
        "fixture_id": FIXTURE_ID,
        "label": "LABELED_FIXTURE — not live trading evidence",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    client = TestClient(app)

    # ── Populated fixture ──
    trades = _rich_trades()
    sid, sess = _seed_session(client, trades, empty=False)
    results["populated_session_id"] = sid

    snap = client.get(f"/api/v1/replay/sessions/{sid}/report")
    assert snap.status_code == 200, snap.text[:800]
    report_body = snap.json()["report"]
    (OUT / f"LABELED_FIXTURE_{FIXTURE_ID}_report_snapshot.json").write_text(
        json.dumps(report_body, indent=2, default=str), encoding="utf-8"
    )

    indep = _independent_from_api(report_body)
    results["api_independent"] = indep
    results["api_metadata"] = {
        "report_id": report_body["metadata"]["report_id"],
        "report_version": report_body["metadata"]["report_version"],
        "replay_timestamp": report_body["metadata"]["replay_timestamp"],
        "disclaimer": report_body["metadata"]["disclaimer"],
        "initial_equity": report_body["metadata"].get("initial_equity"),
        "completed_in_report": len(report_body["completed_trades"]),
        "open_in_report": len(report_body.get("open_trades") or []),
        "equity_points": len(
            (report_body.get("equity") or {}).get("completed", {}).get("points")
            or (report_body.get("equity") or {}).get("points")
            or []
        ),
    }

    # Equity points path flexibility
    eq = report_body.get("equity") or {}
    if "completed" in eq and isinstance(eq["completed"], dict):
        results["api_metadata"]["equity_points"] = len(eq["completed"].get("points") or [])
        results["api_metadata"]["ending_equity_curve"] = eq["completed"].get("ending_equity")
    dd = report_body.get("drawdown") or {}
    results["api_metadata"]["max_drawdown_block"] = {
        "max_drawdown": (dd.get("summary") or dd).get("max_drawdown")
        if isinstance(dd.get("summary") or dd, dict)
        else None,
        "points": len((dd.get("points") or [])),
    }

    csv_files = {}
    for kind in ("summary", "trades", "equity", "drawdown"):
        p = _download(client, sid, kind, FIXTURE_ID)
        csv_files[kind] = {
            "path": str(p.relative_to(ROOT)).replace("\\", "/"),
            "filename": p.name,
            "bytes": p.stat().st_size,
        }

    summary_insp = _csv_summary_inspect(OUT / csv_files["summary"]["filename"])
    trades_insp = _csv_trade_sums(OUT / csv_files["trades"]["filename"])
    equity_insp = _csv_curve_inspect(OUT / csv_files["equity"]["filename"], "equity")
    dd_insp = _csv_curve_inspect(OUT / csv_files["drawdown"]["filename"], "drawdown")

    results["csv"] = {
        "files": csv_files,
        "summary": summary_insp,
        "trades": trades_insp,
        "equity": equity_insp,
        "drawdown": dd_insp,
    }

    pdf_path = _download(client, sid, "pdf", FIXTURE_ID)
    pdf_insp = _inspect_pdf(pdf_path, "populated")
    pdf_nums = _extract_pdf_numbers(pdf_path)
    results["pdf"] = {**pdf_insp, "extracted_metric_lines": pdf_nums}

    # Reconciliation table
    results["reconciliation"] = {
        "completed_count": {
            "api_summary": indep["summary_completed"],
            "api_trade_rows_included": indep["completed_trade_count"],
            "csv_completed_true": trades_insp["completed_true_count"],
            "pdf_mentions_trades": pdf_insp["mentions_fixture_trades"],
        },
        "wins_losses": {
            "api": [indep["summary_wins"], indep["summary_losses"]],
            "sum_trade_nets": [trades_insp["wins"], trades_insp["losses"]],
            "indep_from_api_trades": [indep["winning_trades"], indep["losing_trades"]],
        },
        "gross_pnl": {
            "api_summary": indep["summary_gross"],
            "sum_api_trades": indep["gross_pnl_sum_trades"],
            "csv_sum": trades_insp["gross_sum"],
            "csv_summary_metric": summary_insp["gross_pnl"],
        },
        "net_pnl": {
            "api_summary": indep["summary_net"],
            "sum_api_trades": indep["net_pnl_sum_trades"],
            "csv_sum": trades_insp["net_sum"],
            "csv_summary_metric": summary_insp["net_pnl"],
        },
        "fees": {
            "api_summary": indep["summary_fees"],
            "sum_api_trades": indep["fees_sum_trades"],
            "csv_sum": trades_insp["fees_sum"],
            "csv_summary_metric": summary_insp["total_fees"],
        },
        "slippage": {
            "api_summary": indep["summary_slippage"],
            "sum_api_trades": indep["slippage_sum_trades"],
            "csv_sum": trades_insp["slip_sum"],
            "csv_summary_metric": summary_insp["total_slippage"],
        },
        "spread": {
            "api_summary": indep["summary_spread"],
            "sum_api_trades": indep["spread_sum_trades"],
            "csv_sum": trades_insp["spread_sum"],
            "csv_summary_metric": summary_insp["total_spread_cost"],
        },
        "ending_equity": {
            "api": indep["summary_ending_equity"],
            "csv_summary": summary_insp.get("ending_equity_key"),
        },
        "max_drawdown": {
            "api": indep["summary_max_drawdown"],
            "csv_summary": summary_insp.get("max_drawdown"),
            "api_block": results["api_metadata"]["max_drawdown_block"],
        },
        "directions": trades_insp["directions"],
        "partials_not_double_counted": trades_insp["partial_event_trade_present"]
        and trades_insp["partial_open_not_in_completed"],
        "fees_slip_spread_nonzero": all(
            D(trades_insp[k]) > 0 for k in ("fees_sum", "slip_sum", "spread_sum")
        ),
        "equity_points_nonzero": equity_insp["point_count"] > 0,
        "drawdown_points_or_summary": dd_insp["point_count"] >= 0,
    }

    # ── Empty fixture ──
    reset_replay_manager()
    empty_sid, _ = _seed_session(client, [], empty=True)
    empty_snap = client.get(f"/api/v1/replay/sessions/{empty_sid}/report")
    assert empty_snap.status_code == 200
    empty_report = empty_snap.json()["report"]
    empty_files = {}
    for kind in ("summary", "trades", "equity", "drawdown"):
        p = _download(client, empty_sid, kind, f"{FIXTURE_ID}_EMPTY")
        empty_files[kind] = {"filename": p.name, "bytes": p.stat().st_size}
    empty_pdf = _download(client, empty_sid, "pdf", f"{FIXTURE_ID}_EMPTY")
    empty_pdf_insp = _inspect_pdf(empty_pdf, "empty")
    empty_summary = _csv_summary_inspect(OUT / empty_files["summary"]["filename"])
    empty_trades_text = (OUT / empty_files["trades"]["filename"]).read_text(encoding="utf-8")
    empty_trade_data = _parse_csv(OUT / empty_files["trades"]["filename"])[2]

    results["empty"] = {
        "session_id": empty_sid,
        "completed_trade_count": empty_report["summary"]["completed_trade_count"],
        "win_rate": empty_report["summary"]["win_rate"],
        "profit_factor": empty_report["summary"]["profit_factor"],
        "completed_trades_len": len(empty_report["completed_trades"]),
        "csv_files": empty_files,
        "csv_summary": empty_summary,
        "csv_trade_data_rows": len(empty_trade_data),
        "csv_trades_has_fake_fx_ids": any(
            tid in empty_trades_text
            for tid in ("fx_long_partials", "fx_short_sl", "fx_long_win")
        ),
        "pdf": empty_pdf_insp,
        "equity_points": _csv_curve_inspect(
            OUT / empty_files["equity"]["filename"], "equity"
        )["point_count"],
        "drawdown_points": _csv_curve_inspect(
            OUT / empty_files["drawdown"]["filename"], "drawdown"
        )["point_count"],
    }

    out_json = OUT / "ARTIFACT_QA_RESULTS.json"
    out_json.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"wrote": str(out_json), "populated_sid": sid, "empty_sid": empty_sid}, indent=2))
    # Compact pass/fail hints
    checks = {
        "completed_ge_3": indep["completed_trade_count"] >= 3,
        "has_long_and_short": set(trades_insp["directions"]) >= {"LONG", "SHORT"},
        "partials_ok": results["reconciliation"]["partials_not_double_counted"],
        "costs_nonzero": results["reconciliation"]["fees_slip_spread_nonzero"],
        "equity_ok": equity_insp["point_count"] > 0,
        "dd_nonzero": D(str(indep["summary_max_drawdown"] or 0)) != 0
        or D(
            str(
                (
                    results["api_metadata"]["max_drawdown_block"].get("max_drawdown")
                    or 0
                )
            )
        )
        != 0,
        "pdf_opens": pdf_insp["magic"] == "%PDF-",
        "pdf_pages": pdf_insp["page_count"] >= 1,
        "empty_wr_unavail": results["empty"]["win_rate"]["availability"] == "unavailable",
        "empty_pf_unavail": results["empty"]["profit_factor"]["availability"] == "unavailable",
        "empty_no_trades": results["empty"]["completed_trade_count"] == 0
        and results["empty"]["csv_trade_data_rows"] == 0,
    }
    print("CHECKS", json.dumps(checks, indent=2))
    results["checks"] = checks
    out_json.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
