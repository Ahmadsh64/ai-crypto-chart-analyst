"""CSV export for the backtest report (Phase 5.2.6).

Uses the stdlib ``csv`` module. UTF-8, ISO-8601 UTC timestamps, empty cells
for unavailable metrics (never "0"). Includes a small metadata header block
so a downloaded CSV always identifies the session, symbol, and replay clock.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal
from typing import Iterable

from app.replay.analytics.models import EquityCurve, MetricValue
from app.replay.reporting.config import format_decimal
from app.replay.reporting.enums import ExportKind
from app.replay.reporting.models import BacktestReportSnapshot
from app.replay.reporting.validation import ReportError


# ─── Cell helpers ───


def _iso(ts: datetime | None) -> str:
    if ts is None:
        return ""
    s = ts.isoformat()
    return s.replace("+00:00", "Z")


def _dec(value: Decimal | None) -> str:
    """Decimal → plain string, empty for None. Never emits '0' for unavailable."""
    if value is None:
        return ""
    return format_decimal(value) or ""


def _metric(value: MetricValue | None) -> str:
    if value is None:
        return ""
    if value.availability == "available":
        return _dec(value.value)
    if value.availability == "infinite":
        return "infinite"
    return ""  # unavailable


# ─── Writer ───


def _write_metadata_header(writer: csv.writer, snapshot: BacktestReportSnapshot) -> None:
    meta = snapshot.metadata
    writer.writerow(["# report_id", meta.report_id])
    writer.writerow(["# report_version", meta.report_version])
    writer.writerow(["# session_id", meta.session_id])
    writer.writerow(["# generated_at", _iso(meta.generated_at)])
    writer.writerow(["# exchange", meta.exchange.value])
    writer.writerow(["# symbol", meta.symbol])
    writer.writerow(["# market_type", meta.market_type.value])
    writer.writerow(["# replay_start", _iso(meta.replay_start)])
    writer.writerow(["# replay_end", _iso(meta.replay_end)])
    writer.writerow(["# replay_timestamp", _iso(meta.replay_timestamp)])
    writer.writerow(["# disclaimer", meta.disclaimer])


def _summary_rows(snapshot: BacktestReportSnapshot) -> Iterable[list[str]]:
    s = snapshot.summary
    yield ["metric", "value", "availability", "unit"]
    for km in s.key_metrics:
        yield [
            km.key,
            _dec(km.value) if km.availability == "available"
            else ("infinite" if km.availability == "infinite" else ""),
            km.availability,
            km.unit,
        ]
    # Raw aggregates (always available decimals)
    for key, val in (
        ("completed_trade_count", str(s.completed_trade_count)),
        ("total_simulated_trades", str(s.total_simulated_trades)),
        ("winning_trades", str(s.winning_trades)),
        ("losing_trades", str(s.losing_trades)),
        ("break_even_trades", str(s.break_even_trades)),
        ("partially_closed_trades", str(s.partially_closed_trades)),
        ("open_trades", str(s.open_trades)),
        ("excluded_open_trades", str(s.excluded_open_trades)),
        ("excluded_partial_trades", str(s.excluded_partial_trades)),
        ("gross_pnl", _dec(s.gross_pnl)),
        ("net_pnl", _dec(s.net_pnl)),
        ("total_fees", _dec(s.total_fees)),
        ("total_slippage", _dec(s.total_slippage)),
        ("total_spread_cost", _dec(s.total_spread_cost)),
        ("total_execution_costs", _dec(s.total_execution_costs)),
        ("initial_equity", _dec(s.initial_equity)),
        ("max_drawdown", _dec(s.max_drawdown)),
        ("current_drawdown", _dec(s.current_drawdown)),
    ):
        yield [key, val, "available", ""]


_TRADE_COLUMNS = [
    "trade_id",
    "symbol",
    "direction",
    "lifecycle_status",
    "analytics_class",
    "exit_type",
    "included_in_completed_stats",
    "entry_timestamp_utc",
    "exit_timestamp_utc",
    "entry_price",
    "average_exit_price",
    "original_quantity",
    "executed_quantity",
    "remaining_quantity",
    "initial_stop_loss",
    "current_stop_loss",
    "take_profit_levels",
    "gross_realized_pnl",
    "net_realized_pnl",
    "fees",
    "slippage",
    "spread_cost",
    "r_multiple",
]


def _trade_rows(snapshot: BacktestReportSnapshot) -> Iterable[list[str]]:
    yield _TRADE_COLUMNS
    for row in snapshot.completed_trades:
        yield [
            row.trade_id,
            row.symbol,
            row.direction,
            row.lifecycle_status,
            row.analytics_class,
            row.exit_type,
            "true" if row.included_in_completed_stats else "false",
            _iso(row.entry_timestamp),
            _iso(row.exit_timestamp),
            _dec(row.entry_price),
            _dec(row.average_exit_price),
            _dec(row.original_quantity),
            _dec(row.executed_quantity),
            _dec(row.remaining_quantity),
            _dec(row.initial_stop_loss),
            _dec(row.current_stop_loss),
            ";".join(_dec(v) for v in row.take_profit_levels),
            _dec(row.gross_realized_pnl),
            _dec(row.net_realized_pnl),
            _dec(row.fees),
            _dec(row.slippage),
            _dec(row.spread_cost),
            _dec(row.r_multiple),
        ]
    # Open trades appear as a clearly-separated section.
    if snapshot.open_trades:
        yield []
        yield ["# open_trades_section", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""]
        yield [
            "trade_id",
            "symbol",
            "direction",
            "lifecycle_status",
            "analytics_class",
            "entry_timestamp_utc",
            "entry_price",
            "original_quantity",
            "executed_quantity",
            "remaining_quantity",
            "initial_stop_loss",
            "current_stop_loss",
            "take_profit_levels",
            "note",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ]
        for row in snapshot.open_trades:
            yield [
                row.trade_id,
                row.symbol,
                row.direction,
                row.lifecycle_status,
                row.analytics_class,
                _iso(row.entry_timestamp),
                _dec(row.entry_price),
                _dec(row.original_quantity),
                _dec(row.executed_quantity),
                _dec(row.remaining_quantity),
                _dec(row.initial_stop_loss),
                _dec(row.current_stop_loss),
                ";".join(_dec(v) for v in row.take_profit_levels),
                row.unrealized_note,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ]


def _equity_rows_for(curve: EquityCurve, label: str) -> Iterable[list[str]]:
    yield [
        f"# curve={label}",
        f"mode={curve.mode}",
        f"available={'true' if curve.available else 'false'}",
        f"reason={curve.unavailable_reason or ''}",
        f"initial={_dec(curve.initial_equity)}",
        f"ending={_dec(curve.ending_equity)}",
    ]
    yield [
        "timestamp_utc",
        "trade_id",
        "event_id",
        "net_pnl_change",
        "cumulative_net_pnl",
        "equity",
        "completed_trade_count",
        "curve",
    ]
    for p in curve.points:
        yield [
            _iso(p.timestamp),
            p.trade_id,
            p.event_id or "",
            _dec(p.net_pnl_change),
            _dec(p.cumulative_net_pnl),
            _dec(p.equity),
            str(p.completed_trade_count),
            p.curve,
        ]


def _equity_rows(snapshot: BacktestReportSnapshot) -> Iterable[list[str]]:
    yield from _equity_rows_for(snapshot.equity.completed, "completed_trade")
    yield []
    yield from _equity_rows_for(snapshot.equity.cashflow, "realized_cashflow")


def _drawdown_rows(snapshot: BacktestReportSnapshot) -> Iterable[list[str]]:
    dd = snapshot.drawdown.summary
    yield [
        "# available",
        "true" if dd.available else "false",
        "reason",
        dd.unavailable_reason or "",
    ]
    yield [
        "# max_drawdown",
        _dec(dd.max_drawdown),
        "max_drawdown_pct",
        _metric(dd.max_drawdown_pct),
    ]
    yield [
        "# peak",
        _iso(dd.peak_timestamp),
        "trough",
        _iso(dd.trough_timestamp),
        "recovery",
        _iso(dd.recovery_timestamp),
    ]
    yield ["timestamp_utc", "equity", "peak_equity", "drawdown", "drawdown_pct"]
    for p in snapshot.drawdown.points:
        yield [
            _iso(p.timestamp),
            _dec(p.equity),
            _dec(p.peak_equity),
            _dec(p.drawdown),
            _dec(p.drawdown_pct),
        ]


_RENDERERS = {
    "summary": _summary_rows,
    "trades": _trade_rows,
    "equity": _equity_rows,
    "drawdown": _drawdown_rows,
}


def render_csv(snapshot: BacktestReportSnapshot, kind: ExportKind) -> bytes:
    if kind not in _RENDERERS:
        raise ReportError(f"Unknown CSV export kind: {kind}")
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    _write_metadata_header(writer, snapshot)
    writer.writerow([])
    for row in _RENDERERS[kind](snapshot):
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")
