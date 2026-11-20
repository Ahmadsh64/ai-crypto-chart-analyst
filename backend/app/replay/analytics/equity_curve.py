"""Deterministic equity curve builders (Phase 5.2.4)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.replay.analytics.models import EquityCurve, EquityPoint
from app.replay.analytics.trade_filter import ClassifiedTrade
from app.replay.costs.models import LedgerEntry
from app.replay.timeline import ensure_utc

ZERO = Decimal("0")


def _q(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.00000001"))


def build_completed_trade_curve(
    completed: list[ClassifiedTrade],
    *,
    initial_equity: Decimal | None,
) -> EquityCurve:
    """One point per fully closed trade at exit timestamp (tie-break: trade_id)."""
    events: list[tuple[datetime, str, str | None, Decimal]] = []
    for item in completed:
        assert item.cost is not None
        t = item.trade
        ts = ensure_utc(t.exit_timestamp or t.updated_at or t.decision_timestamp)
        events.append((ts, t.trade_id, None, item.cost.net_realized_pnl))
    events.sort(key=lambda e: (e[0], e[1]))
    return _accumulate(events, mode="completed_trade", initial_equity=initial_equity)


def build_cashflow_curve_from_ledger(
    all_entries: list[LedgerEntry],
    *,
    initial_equity: Decimal | None,
    include_partial: bool,
    completed_ids: set[str],
) -> EquityCurve:
    """
    Realized cash-flow equity from exit ledger legs.

    Exit ``net_realized_pnl`` already deducts allocated entry fees + exit costs.
    Entry slip/spread (not in exit nets) is deducted once on the first exit of
    each trade so cumulative cashflow matches CostEngine trade net.
    """
    by_trade_exits: dict[str, list[LedgerEntry]] = {}
    entry_slip_spread: dict[str, Decimal] = {}
    for e in all_entries:
        if e.execution_role == "entry":
            entry_slip_spread[e.trade_id] = entry_slip_spread.get(e.trade_id, ZERO) + (
                e.slippage_amount + e.spread_cost
            )
        elif e.execution_role == "exit" and e.net_realized_pnl is not None:
            by_trade_exits.setdefault(e.trade_id, []).append(e)

    events: list[tuple[datetime, str, str | None, Decimal]] = []
    for tid, exits in by_trade_exits.items():
        if not include_partial and tid not in completed_ids:
            continue
        exits_sorted = sorted(
            exits, key=lambda x: (ensure_utc(x.event_timestamp), x.source_event_id)
        )
        entry_adj = entry_slip_spread.get(tid, ZERO)
        first = True
        for e in exits_sorted:
            change = e.net_realized_pnl or ZERO
            if first and entry_adj:
                change = change - entry_adj
                first = False
            events.append(
                (ensure_utc(e.event_timestamp), tid, e.source_event_id, change)
            )

    events.sort(key=lambda x: (x[0], x[1], x[2] or ""))
    return _accumulate(events, mode="realized_cashflow", initial_equity=initial_equity)


def _accumulate(
    events: list[tuple[datetime, str, str | None, Decimal]],
    *,
    mode: str,
    initial_equity: Decimal | None,
) -> EquityCurve:
    points: list[EquityPoint] = []
    cum = ZERO
    seen_trades: set[str] = set()
    for ts, trade_id, event_id, change in events:
        cum = _q(cum + change)
        seen_trades.add(trade_id)
        equity = _q(initial_equity + cum) if initial_equity is not None else None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        points.append(
            EquityPoint(
                timestamp=ts,
                trade_id=trade_id,
                event_id=event_id,
                net_pnl_change=_q(change),
                cumulative_net_pnl=cum,
                equity=equity,
                completed_trade_count=len(seen_trades),
                curve=mode,
            )
        )

    ending = _q(initial_equity + cum) if initial_equity is not None else None
    return EquityCurve(
        mode=mode,
        points=points,
        available=True,
        initial_equity=initial_equity,
        ending_equity=ending,
        cumulative_net_pnl=cum,
    )


def empty_curve(
    mode: str, initial_equity: Decimal | None, reason: str | None = None
) -> EquityCurve:
    return EquityCurve(
        mode=mode,
        points=[],
        available=reason is None,
        unavailable_reason=reason,
        initial_equity=initial_equity,
        ending_equity=initial_equity,
        cumulative_net_pnl=ZERO,
    )
