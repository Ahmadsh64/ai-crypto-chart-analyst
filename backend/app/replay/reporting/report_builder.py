"""Assemble the backtest report snapshot from session state (Phase 5.2.6).

Read-only. Does not mutate simulation, cost, or analytics engines.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.replay.analytics.config import ANALYTICS_VERSION
from app.replay.analytics.trade_filter import ClassifiedTrade, classify_trade
from app.replay.reporting.config import DEFAULT_REPORT_CONFIG, ReportConfig
from app.replay.reporting.models import (
    BacktestReportSnapshot,
    ReportDrawdownSection,
    ReportEquitySection,
    ReportMetadata,
)
from app.replay.reporting.summary_builder import build_report_summary
from app.replay.reporting.trade_serializer import (
    build_completed_trade_detail,
    build_open_trade,
)
from app.replay.reporting.validation import ReportError, assert_no_future_data

if TYPE_CHECKING:
    from app.replay.session import ReplaySession


def build_report(
    session: "ReplaySession",
    *,
    config: ReportConfig | None = None,
    for_export: bool = False,
) -> BacktestReportSnapshot:
    """Build a read-only report snapshot from the current session state.

    ``for_export=True`` skips inline truncation so CSV/PDF contain the full set.
    """
    cfg = config or DEFAULT_REPORT_CONFIG

    if not session.analytics_engine.enabled:
        raise ReportError(
            "Performance analytics must be enabled before generating a report."
        )
    if not session.event_times:
        raise ReportError("Replay session has no events; cannot generate report.")

    clock = session.event_times[session.event_index]
    trades = list(session.simulator.trades.values())
    cost_engine = session.cost_engine

    analytics_snap = session.analytics_engine.snapshot(
        trades,
        cost_engine,
        replay_timestamp=clock,
        event_index=session.event_index,
        filt=session.analytics_filter,
    )

    # Classify every trade using the same filter / policy the analytics engine used.
    filt = session.analytics_filter
    cost_by_id = {
        s.trade_id: s for s in cost_engine.snapshot(trades, replay_timestamp=clock).trades
    }
    classified: list[ClassifiedTrade] = []
    for t in sorted(trades, key=lambda x: (x.decision_timestamp, x.trade_id)):
        c = classify_trade(
            t,
            cost_by_id.get(t.trade_id),
            include_ambiguous_as_closed_when_flat=(
                session.analytics_config.include_ambiguous_as_closed_when_flat
            ),
        )
        if filt and not filt.matches(c):
            continue
        classified.append(c)

    def _visible(item: ClassifiedTrade) -> bool:
        t = item.trade
        if t.entry_timestamp is not None and t.entry_timestamp > clock:
            return False
        if item.is_completed and t.exit_timestamp is not None and t.exit_timestamp > clock:
            return False
        return True

    visible = [c for c in classified if _visible(c)]
    completed_items = [c for c in visible if c.is_completed]
    open_items = [c for c in visible if not c.is_completed]

    completed_details = [
        build_completed_trade_detail(c, cost_engine) for c in completed_items
    ]
    open_details = [build_open_trade(c) for c in open_items]

    completed_total = len(completed_details)
    open_total = len(open_details)

    completed_truncated = (
        False if for_export else completed_total > cfg.max_inline_completed_trades
    )
    open_truncated = False if for_export else open_total > cfg.max_inline_open_trades
    if completed_truncated:
        completed_details = completed_details[: cfg.max_inline_completed_trades]
    if open_truncated:
        open_details = open_details[: cfg.max_inline_open_trades]

    info = session.info()
    metadata = ReportMetadata(
        report_id="rep_" + uuid.uuid4().hex[:16],
        report_version=cfg.config_version,
        session_id=session.session_id,
        generated_at=datetime.now(timezone.utc),
        replay_timestamp=clock,
        event_index=session.event_index,
        event_count=len(session.event_times),
        exchange=session.exchange,
        symbol=session.symbol,
        market_type=session.market_type,
        timeframes=list(session.timeframes),
        replay_start=session.start_time,
        replay_end=session.end_time,
        status=session.status,
        data_quality=info.data_quality,
        initial_equity=analytics_snap.summary.initial_equity,
        initial_equity_source=analytics_snap.summary.initial_equity_source,
        quote_currency=session.analytics_config.quote_currency,
        disclaimer=cfg.disclaimer,
        filter_context=analytics_snap.summary.filter_context,
        cost_model_version=analytics_snap.summary.cost_model_version,
        analytics_version=ANALYTICS_VERSION,
    )

    summary = build_report_summary(analytics_snap.summary)
    equity_completed = analytics_snap.equity_completed.model_copy(deep=True)
    equity_cashflow = analytics_snap.equity_cashflow.model_copy(deep=True)
    equity_completed.points = [
        p for p in equity_completed.points if p.timestamp <= clock
    ]
    equity_cashflow.points = [
        p for p in equity_cashflow.points if p.timestamp <= clock
    ]
    equity = ReportEquitySection(
        completed=equity_completed,
        cashflow=equity_cashflow,
    )
    dd_summary = analytics_snap.drawdown.model_copy(deep=True)
    dd_points = [p for p in dd_summary.series if p.timestamp <= clock]
    dd_summary.series = dd_points
    drawdown = ReportDrawdownSection(
        summary=dd_summary,
        points=dd_points,
    )

    limitations: list[str] = []
    assumptions: list[str] = list(analytics_snap.summary.assumptions)
    if completed_truncated:
        limitations.append(
            f"Inline completed_trades truncated to first "
            f"{cfg.max_inline_completed_trades} of {completed_total} — use CSV export for full set."
        )
    if open_truncated:
        limitations.append(
            f"Inline open_trades truncated to first "
            f"{cfg.max_inline_open_trades} of {open_total}."
        )
    if filt and any(
        [
            filt.exchange,
            filt.symbol,
            filt.market_type,
            filt.direction,
            filt.exit_type,
            filt.start_time_iso,
            filt.end_time_iso,
        ]
    ):
        limitations.append(
            "Report reflects an active analytics filter — not the complete session."
        )
    missing_exit_vwap = [
        row for row in completed_details if row.average_exit_price is None
    ]
    if missing_exit_vwap:
        limitations.append(
            f"{len(missing_exit_vwap)} completed trade(s) have no exit ledger fills "
            "— average_exit_price reported as unavailable."
        )

    snapshot = BacktestReportSnapshot(
        metadata=metadata,
        summary=summary,
        performance_summary=analytics_snap.summary,
        equity=equity,
        drawdown=drawdown,
        groups=analytics_snap.groups,
        completed_trades=completed_details,
        completed_trade_total=completed_total,
        completed_trades_truncated=completed_truncated,
        open_trades=open_details,
        open_trade_total=open_total,
        open_trades_truncated=open_truncated,
        limitations=limitations,
        assumptions=assumptions,
        disclaimer=cfg.disclaimer,
    )

    assert_no_future_data(snapshot, clock=clock)
    return snapshot


def classify_all(
    session: "ReplaySession",
) -> list[ClassifiedTrade]:
    """Helper used by tests: classify trades with the session's analytics policy."""
    trades = list(session.simulator.trades.values())
    cost_snap = session.cost_engine.snapshot(
        trades,
        replay_timestamp=(
            session.event_times[session.event_index] if session.event_times else None
        ),
    )
    cost_by_id = {s.trade_id: s for s in cost_snap.trades}
    return [
        classify_trade(
            t,
            cost_by_id.get(t.trade_id),
            include_ambiguous_as_closed_when_flat=(
                session.analytics_config.include_ambiguous_as_closed_when_flat
            ),
        )
        for t in trades
    ]
