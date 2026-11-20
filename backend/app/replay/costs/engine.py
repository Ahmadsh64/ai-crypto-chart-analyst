"""Execution cost engine — consumes Phase 5.2.2 simulation events (Phase 5.2.3)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from app.replay.costs.config import COST_MODEL_VERSION, ExecutionCostConfig, default_cost_config
from app.replay.costs.enums import (
    ExecutionRole,
    MakerTakerClass,
    OrderTypeEstimate,
)
from app.replay.costs.fee_calculator import applicable_fee_rate, calculate_fee
from app.replay.costs.ledger import ExecutionLedger
from app.replay.costs.models import (
    CostSnapshot,
    LedgerEntry,
    SessionCostSummary,
    TradeCostSummary,
)
from app.replay.costs.pnl_calculator import allocate_entry_fee, gross_pnl, net_pnl
from app.replay.costs.slippage_calculator import apply_slippage, slippage_cost_for_qty
from app.replay.costs.spread_calculator import apply_half_spread, spread_cost_for_qty
from app.replay.costs.validation import d, reconcile_trade_summary
from app.replay.simulation.models import SimulatedTrade, SimulationExecutionEvent

logger = logging.getLogger(__name__)

# Simulation event types that represent executable fills.
_ENTRY_EVENTS = frozenset({"trade_opened"})
_EXIT_EVENTS = frozenset({"trade_partially_closed", "trade_closed", "trade_ambiguous"})


@dataclass
class _TradeCostState:
    entry_fee_total: Decimal = Decimal("0")
    entry_fee_allocated: Decimal = Decimal("0")
    entry_qty: Decimal = Decimal("0")
    entry_execution_price: Decimal | None = None  # cost-adjusted VWAP if multiple
    entry_notional: Decimal = Decimal("0")
    processed_event_ids: set[str] = field(default_factory=set)


class CostEngine:
    """Isolated cost layer. Does not generate signals or change 5.2.2 fills."""

    def __init__(
        self,
        *,
        session_id: str,
        config: ExecutionCostConfig | None = None,
    ) -> None:
        self.session_id = session_id
        self.config = config or default_cost_config()
        self.enabled = False
        self.ledger = ExecutionLedger()
        self._trade_state: dict[str, _TradeCostState] = {}
        self._emitted_execution_ids: set[str] = set()

    def reset(self) -> None:
        self.ledger.reset()
        self._trade_state.clear()
        self._emitted_execution_ids.clear()

    def enable(self) -> None:
        self.enabled = True
        self.config.enabled = True

    def disable(self) -> None:
        self.enabled = False
        self.config.enabled = False

    def update_config(self, config: ExecutionCostConfig) -> None:
        """Replace config. Caller must rebuild ledger after fee/slippage changes."""
        was = self.enabled
        self.config = config
        self.config.enabled = was
        self.enabled = was

    def process_trades(
        self,
        trades: list[SimulatedTrade],
    ) -> list[LedgerEntry]:
        """Process any new fill events from simulated trades. Idempotent by event_id."""
        if not self.enabled:
            return []
        new_entries: list[LedgerEntry] = []
        for trade in sorted(trades, key=lambda t: (t.decision_timestamp, t.trade_id)):
            for ev in trade.execution_events:
                entry = self._process_event(trade, ev)
                if entry is not None:
                    new_entries.append(entry)
        return new_entries

    def rebuild_from_trades(self, trades: list[SimulatedTrade]) -> list[LedgerEntry]:
        """Clear and deterministically rebuild ledger from all trade events."""
        self.reset()
        if not self.enabled:
            return []
        return self.process_trades(trades)

    def _state(self, trade_id: str) -> _TradeCostState:
        if trade_id not in self._trade_state:
            self._trade_state[trade_id] = _TradeCostState()
        return self._trade_state[trade_id]

    def _process_event(
        self,
        trade: SimulatedTrade,
        ev: SimulationExecutionEvent,
    ) -> LedgerEntry | None:
        if self.ledger.has_source(ev.event_id):
            return None
        if ev.event_type in _ENTRY_EVENTS:
            return self._process_fill(trade, ev, role="entry")
        if ev.event_type in _EXIT_EVENTS:
            if ev.price is None or ev.quantity is None:
                return None
            if d(ev.quantity) <= 0:
                return None
            st = self._state(trade.trade_id)
            if st.entry_qty <= 0 and trade.entry_price is None:
                if trade.lifecycle_status in {"rejected", "cancelled", "pending_entry"}:
                    return None
            # Same-candle entry+exit may emit only trade_ambiguous — ensure entry fee once.
            if (
                ev.event_type == "trade_ambiguous"
                and st.entry_qty <= 0
                and trade.entry_price is not None
                and trade.executed_quantity > 0
            ):
                synthetic = SimulationExecutionEvent(
                    event_id=f"{ev.event_id}|entry",
                    event_type="trade_opened",
                    timestamp=ev.timestamp,
                    price=trade.entry_price,
                    quantity=trade.executed_quantity,
                    reason="Synthetic entry for ambiguous same-candle fill (cost layer).",
                )
                self._process_fill(trade, synthetic, role="entry")
            return self._process_fill(trade, ev, role="exit")
        return None

    def _classify(
        self,
        trade: SimulatedTrade,
        ev: SimulationExecutionEvent,
        role: ExecutionRole,
    ) -> tuple[MakerTakerClass, OrderTypeEstimate, list[str]]:
        """Heuristic classification from existing fill context — not exchange-confirmed."""
        assumptions: list[str] = [
            "Maker/taker classification is estimated from OHLCV fill context, "
            "not exchange-confirmed."
        ]
        ref = d(ev.price)
        if role == "entry":
            limit = trade.entry_limit_price
            if limit is not None and abs(ref - d(limit)) <= Decimal("1e-12"):
                return "maker", "limit", assumptions
            if limit is not None and abs(ref - d(limit)) > Decimal("1e-12"):
                # Gap / open-through → immediately marketable
                return "taker", "marketable_limit", assumptions
            return "unknown", "unknown", assumptions

        # Exits
        reason = (ev.reason or "").lower()
        if "stop" in reason or "stop loss" in reason:
            return "taker", "stop", assumptions
        if ev.tp_index is not None:
            # TP at exact level ≈ resting limit; otherwise gap ≈ taker
            levels = trade.take_profit_levels
            if 0 <= ev.tp_index < len(levels):
                tp = d(levels[ev.tp_index])
                if abs(ref - tp) <= Decimal("1e-12"):
                    return "maker", "limit", assumptions
                return "taker", "marketable_limit", assumptions
            return "unknown", "limit", assumptions
        return "unknown", "unknown", assumptions

    def _process_fill(
        self,
        trade: SimulatedTrade,
        ev: SimulationExecutionEvent,
        *,
        role: ExecutionRole,
    ) -> LedgerEntry | None:
        if ev.price is None or ev.quantity is None:
            return None
        qty = d(ev.quantity)
        if qty <= 0:
            return None
        ref = d(ev.price)
        if ref <= 0:
            return None

        schedule = self.config.resolve_fee_schedule(trade.exchange, trade.market_type)
        mt_class, order_type, mt_assumptions = self._classify(trade, ev, role)
        fee_rate, effective_mt, mt_warnings = applicable_fee_rate(
            mt_class,
            schedule,
            fallback=self.config.maker_taker_fallback,
        )

        assumptions = list(mt_assumptions)
        warnings = list(mt_warnings)

        # Slippage then half-spread on reference → cost-layer execution price
        slipped, slip_delta, slip_warn = apply_slippage(
            ref,
            direction=trade.direction,
            role=role,
            config=self.config,
        )
        warnings.extend(slip_warn)
        spread_adj, half_spread, spread_assump, spread_warn = apply_half_spread(
            slipped,
            direction=trade.direction,
            role=role,
            config=self.config,
        )
        assumptions.extend(spread_assump)
        warnings.extend(spread_warn)

        exec_price = spread_adj
        mult = self.config.contract_multiplier
        notional = (qty * exec_price * mult).quantize(Decimal("0.00000001"))
        fee_amt = calculate_fee(notional, fee_rate)
        slip_cost = slippage_cost_for_qty(slip_delta, qty * mult)
        spread_cost = spread_cost_for_qty(half_spread, qty * mult)

        st = self._state(trade.trade_id)
        gross: Decimal | None = None
        allocated_entry: Decimal | None = None
        net: Decimal | None = None

        if role == "entry":
            prev_q = st.entry_qty
            if st.entry_execution_price is None or prev_q <= 0:
                st.entry_execution_price = exec_price
            else:
                st.entry_execution_price = (
                    (st.entry_execution_price * prev_q) + (exec_price * qty)
                ) / (prev_q + qty)
            st.entry_fee_total += fee_amt
            st.entry_qty += qty
            st.entry_notional += notional
        else:
            entry_px = st.entry_execution_price
            if entry_px is None and trade.entry_price is not None:
                entry_px = d(trade.entry_price)
                assumptions.append(
                    "Exit priced against Phase 5.2.2 entry_price (no prior cost entry)."
                )
            if entry_px is None:
                warnings.append("Missing entry price for exit P&L; gross/net unavailable.")
            else:
                original = d(trade.original_quantity) if trade.original_quantity else st.entry_qty
                if original <= 0:
                    original = st.entry_qty if st.entry_qty > 0 else qty
                allocated_entry = allocate_entry_fee(
                    st.entry_fee_total,
                    exit_qty=qty,
                    original_qty=original,
                )
                # Cap allocation so we never exceed remaining unallocated entry fees
                remaining_fee = st.entry_fee_total - st.entry_fee_allocated
                if allocated_entry > remaining_fee:
                    allocated_entry = remaining_fee
                st.entry_fee_allocated += allocated_entry

                gross = gross_pnl(
                    direction=trade.direction,
                    entry_price=entry_px,
                    exit_price=exec_price,
                    quantity=qty,
                    multiplier=mult,
                )
                # Exit-row net: allocated entry fee + this exit's fee/slip/spread.
                # Entry slip/spread stay on entry rows; trade_summary subtracts them once.
                net = net_pnl(
                    gross=gross,
                    entry_fee_allocated=allocated_entry,
                    exit_fee=fee_amt,
                    slippage_cost=slip_cost,
                    spread_cost=spread_cost,
                )

        execution_id = f"ec_{ev.event_id}"
        entry = LedgerEntry(
            execution_id=execution_id,
            source_event_id=ev.event_id,
            trade_id=trade.trade_id,
            replay_session_id=self.session_id,
            event_timestamp=ev.timestamp,
            exchange=trade.exchange,
            market_type=trade.market_type,
            symbol=trade.symbol,
            direction=trade.direction,
            execution_role=role,
            order_type_estimate=order_type,
            maker_taker=effective_mt if mt_class == "unknown" else mt_class,
            maker_taker_estimated=True,
            executed_quantity=qty,
            reference_price=ref,
            execution_price=exec_price,
            executed_notional=notional,
            fee_rate=fee_rate,
            fee_amount=fee_amt,
            slippage_amount=slip_cost,
            spread_cost=spread_cost,
            gross_realized_pnl=gross,
            allocated_entry_fee=allocated_entry,
            net_realized_pnl=net,
            cost_model_version=self.config.config_version or COST_MODEL_VERSION,
            fee_config_source=schedule.source,
            fee_schedule_version=schedule.schedule_version,
            assumptions=assumptions,
            warnings=warnings,
            metadata={
                "simulation_event_type": ev.event_type,
                "tp_index": ev.tp_index,
                "reason": ev.reason,
            },
        )
        if self.ledger.append(entry):
            st.processed_event_ids.add(ev.event_id)
            return entry
        return None

    def trade_summary(self, trade: SimulatedTrade) -> TradeCostSummary:
        entries = self.ledger.for_trade(trade.trade_id)
        entry_fees = sum(
            (e.fee_amount for e in entries if e.execution_role == "entry"),
            Decimal("0"),
        )
        exit_fees = sum(
            (e.fee_amount for e in entries if e.execution_role == "exit"),
            Decimal("0"),
        )
        slip = sum((e.slippage_amount for e in entries), Decimal("0"))
        spread = sum((e.spread_cost for e in entries), Decimal("0"))
        gross = sum(
            (e.gross_realized_pnl or Decimal("0") for e in entries if e.execution_role == "exit"),
            Decimal("0"),
        )
        # Net = sum of exit nets minus... exit nets already deduct allocated entry fees
        # and exit fees/slip/spread. Entry slip/spread still need inclusion in total costs.
        exit_nets = sum(
            (e.net_realized_pnl or Decimal("0") for e in entries if e.execution_role == "exit"),
            Decimal("0"),
        )
        entry_slip_spread = sum(
            (
                e.slippage_amount + e.spread_cost
                for e in entries
                if e.execution_role == "entry"
            ),
            Decimal("0"),
        )
        net = (exit_nets - entry_slip_spread).quantize(Decimal("0.00000001"))
        total_fees = entry_fees + exit_fees
        total_costs = (total_fees + slip + spread).quantize(Decimal("0.00000001"))

        schedule = self.config.resolve_fee_schedule(trade.exchange, trade.market_type)
        assumptions: list[str] = []
        warnings: list[str] = []
        for e in entries:
            assumptions.extend(e.assumptions)
            warnings.extend(e.warnings)
        # Dedupe preserving order
        assumptions = list(dict.fromkeys(assumptions))
        warnings = list(dict.fromkeys(warnings))

        summary = TradeCostSummary(
            trade_id=trade.trade_id,
            session_id=self.session_id,
            symbol=trade.symbol,
            direction=trade.direction,
            lifecycle_status=trade.lifecycle_status,
            total_executed_quantity=d(trade.executed_quantity),
            remaining_open_quantity=d(trade.remaining_quantity),
            total_gross_realized_pnl=gross,
            total_entry_fees=entry_fees,
            total_exit_fees=exit_fees,
            total_fees=total_fees,
            total_slippage=slip,
            total_spread_cost=spread,
            total_costs=total_costs,
            net_realized_pnl=net,
            cost_model_version=self.config.config_version,
            fee_config_source=schedule.source,
            assumptions=assumptions,
            warnings=warnings,
            ledger_entry_count=len(entries),
        )
        summary.warnings.extend(reconcile_trade_summary(summary))
        return summary

    def session_summary(
        self,
        trades: list[SimulatedTrade],
        *,
        replay_timestamp: datetime | None = None,
    ) -> SessionCostSummary:
        trade_summaries = [self.trade_summary(t) for t in trades if self.ledger.for_trade(t.trade_id)]
        # Also include empty for opened trades with ledger
        if not trade_summaries:
            # Build from any ledger trade ids
            seen = {e.trade_id for e in self.ledger.all_entries()}
            by_id = {t.trade_id: t for t in trades}
            for tid in seen:
                if tid in by_id:
                    trade_summaries.append(self.trade_summary(by_id[tid]))

        gross = sum((s.total_gross_realized_pnl for s in trade_summaries), Decimal("0"))
        entry_fees = sum((s.total_entry_fees for s in trade_summaries), Decimal("0"))
        exit_fees = sum((s.total_exit_fees for s in trade_summaries), Decimal("0"))
        fees = entry_fees + exit_fees
        slip = sum((s.total_slippage for s in trade_summaries), Decimal("0"))
        spread = sum((s.total_spread_cost for s in trade_summaries), Decimal("0"))
        costs = fees + slip + spread
        net = sum((s.net_realized_pnl for s in trade_summaries), Decimal("0"))

        # Fee source from config resolution using first trade or defaults
        if trades:
            sch = self.config.resolve_fee_schedule(trades[0].exchange, trades[0].market_type)
        else:
            from app.exchanges.types import ExchangeId, MarketType

            sch = self.config.resolve_fee_schedule(ExchangeId.BINANCE, MarketType.SPOT)

        assumptions = list(
            dict.fromkeys(a for s in trade_summaries for a in s.assumptions)
        )
        warnings = list(dict.fromkeys(w for s in trade_summaries for w in s.warnings))
        if sch.source == "example_default":
            assumptions.append(
                "Fee rates are EXAMPLE DEFAULTS for simulation — configure your account rates."
            )

        return SessionCostSummary(
            session_id=self.session_id,
            enabled=self.enabled,
            cost_model_version=self.config.config_version,
            fee_config_source=sch.source,
            fee_schedule_version=sch.schedule_version,
            gross_realized_pnl=gross,
            total_entry_fees=entry_fees,
            total_exit_fees=exit_fees,
            total_fees=fees,
            total_slippage=slip,
            total_spread_cost=spread,
            total_costs=costs,
            net_realized_pnl=net,
            trade_count=len(trade_summaries),
            ledger_entry_count=len(self.ledger),
            assumptions=assumptions,
            warnings=warnings,
            disclaimer=self.config.disclaimer,
            config=self.config.snapshot(),
            replay_timestamp=replay_timestamp,
        )

    def snapshot(
        self,
        trades: list[SimulatedTrade],
        *,
        replay_timestamp: datetime | None = None,
    ) -> CostSnapshot:
        summary = self.session_summary(trades, replay_timestamp=replay_timestamp)
        trade_sums = []
        for t in trades:
            if self.ledger.for_trade(t.trade_id):
                trade_sums.append(self.trade_summary(t))
        recent = self.ledger.all_entries()[-50:]
        return CostSnapshot(
            session_id=self.session_id,
            enabled=self.enabled,
            summary=summary,
            trades=trade_sums,
            recent_ledger=recent,
            cost_model_version=self.config.config_version,
            disclaimer=self.config.disclaimer,
        )
