"""Historical trade simulator core (Phase 5.2.2)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.replay.analysis.models import HistoricalAnalysisSnapshot
from app.replay.simulation.config import DEFAULT_SIMULATION_CONFIG, SimulationConfig
from app.replay.simulation.eligibility import evaluate_eligibility
from app.replay.simulation.entry_execution import try_fill_entry
from app.replay.simulation.exit_execution import resolve_same_candle_order
from app.replay.simulation.lifecycle import append_event, new_trade_id
from app.replay.simulation.models import (
    SimulatedTrade,
    SimulationExecutionEvent,
    SimulationOverview,
    SimulationSnapshot,
)
from app.replay.simulation.validation import assert_quantities
from app.replay.timeline import candle_close_time, ensure_utc

logger = logging.getLogger(__name__)


class TradeSimulator:
    """Consumes analysis snapshots + subsequent execution candles. No signal generation."""

    def __init__(
        self,
        *,
        session_id: str,
        config: SimulationConfig | None = None,
    ) -> None:
        self.session_id = session_id
        self.config = config or DEFAULT_SIMULATION_CONFIG
        self.enabled = False
        self.trades: dict[str, SimulatedTrade] = {}
        self._signal_keys: set[str] = set()
        self._events: list[SimulationExecutionEvent] = []
        self._emitted_event_ids: set[str] = set()

    def reset(self) -> None:
        self.trades.clear()
        self._signal_keys.clear()
        self._events.clear()
        self._emitted_event_ids.clear()

    def enable(self) -> None:
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False

    def overview(self, replay_timestamp: datetime | None = None) -> SimulationOverview:
        trades = list(self.trades.values())
        return SimulationOverview(
            enabled=self.enabled,
            pending_count=sum(1 for t in trades if t.lifecycle_status == "pending_entry"),
            open_count=sum(1 for t in trades if t.lifecycle_status == "open"),
            partially_closed_count=sum(
                1 for t in trades if t.lifecycle_status == "partially_closed"
            ),
            closed_count=sum(
                1
                for t in trades
                if t.lifecycle_status in {"closed_tp", "closed_sl", "closed_expired"}
            ),
            rejected_count=sum(1 for t in trades if t.lifecycle_status == "rejected"),
            cancelled_count=sum(1 for t in trades if t.lifecycle_status == "cancelled"),
            ambiguous_count=sum(
                1 for t in trades if t.lifecycle_status == "ambiguous_execution"
            ),
            total_trades=len(trades),
            config=self.config.snapshot(),
            disclaimer=self.config.disclaimer,
            replay_timestamp=replay_timestamp,
        )

    def snapshot(self, replay_timestamp: datetime | None = None) -> SimulationSnapshot:
        trades = sorted(
            self.trades.values(),
            key=lambda t: (t.decision_timestamp, t.trade_id),
        )
        return SimulationSnapshot(
            session_id=self.session_id,
            enabled=self.enabled,
            overview=self.overview(replay_timestamp),
            trades=trades,
            recent_events=self._events[-50:],
            config_version=self.config.config_version,
            disclaimer=self.config.disclaimer,
        )

    def list_trades(
        self,
        *,
        status: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[SimulatedTrade], int]:
        items = list(self.trades.values())
        if status:
            items = [t for t in items if t.lifecycle_status == status]
        items.sort(key=lambda t: (t.decision_timestamp, t.trade_id))
        total = len(items)
        return items[offset : offset + limit], total

    def get_trade(self, trade_id: str) -> SimulatedTrade | None:
        return self.trades.get(trade_id)

    def list_events(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[SimulationExecutionEvent], int]:
        total = len(self._events)
        return self._events[offset : offset + limit], total

    def process_tick(
        self,
        *,
        analysis: HistoricalAnalysisSnapshot | None,
        execution_candle: Candle | None,
        series_by_tf: dict[Timeframe, list[Candle]],
        clock: datetime,
        event_index: int,
    ) -> list[SimulationExecutionEvent]:
        """
        One replay tick after analysis.

        Order: eligibility → create pending → process entries → process exits.
        """
        if not self.enabled:
            return []

        clock = ensure_utc(clock)
        new_events: list[SimulationExecutionEvent] = []

        if analysis is not None:
            new_events.extend(self._maybe_create_from_analysis(analysis, event_index))

        if execution_candle is not None:
            tf = self.config.execution_timeframe
            # Strict: only candles that closed at this clock and after decision
            if candle_close_time(execution_candle, tf) == clock:
                new_events.extend(
                    self._process_pending_entries(execution_candle, clock, series_by_tf)
                )
                new_events.extend(
                    self._process_open_exits(execution_candle, clock, series_by_tf)
                )

        # Expire pending that passed expires_at without fill
        new_events.extend(self._expire_pending(clock))

        for ev in new_events:
            if ev.event_id not in self._emitted_event_ids:
                self._emitted_event_ids.add(ev.event_id)
                self._events.append(ev)

        # Bound memory
        max_t = self.config.max_trades_tracked
        if len(self.trades) > max_t:
            # Drop oldest closed/rejected first
            closable = sorted(
                [
                    t
                    for t in self.trades.values()
                    if t.lifecycle_status
                    in {
                        "closed_tp",
                        "closed_sl",
                        "closed_expired",
                        "cancelled",
                        "rejected",
                    }
                ],
                key=lambda t: t.updated_at,
            )
            for t in closable[: max(0, len(self.trades) - max_t)]:
                self.trades.pop(t.trade_id, None)

        return [e for e in new_events if e.event_id in self._emitted_event_ids]

    def _maybe_create_from_analysis(
        self,
        snap: HistoricalAnalysisSnapshot,
        event_index: int,
    ) -> list[SimulationExecutionEvent]:
        result = evaluate_eligibility(snap, config=self.config)
        if not result.eligible:
            # Optionally record rejections for LONG/SHORT attempts only
            decision = str(snap.decision).upper()
            if decision in {"LONG", "SHORT"} and result.signal_key:
                # Don't spam identical rejections
                reject_key = result.signal_key + "|rejected"
                if reject_key in self._signal_keys:
                    return []
                self._signal_keys.add(reject_key)
                trade = self._build_rejected(snap, result.rejection_reason or "Rejected")
                self.trades[trade.trade_id] = trade
                ev = append_event(
                    trade,
                    event_type="trade_rejected",
                    timestamp=ensure_utc(snap.replay_timestamp),
                    reason=result.rejection_reason,
                )
                return [ev]
            return []

        assert result.signal_key and result.direction and result.entry_limit_price
        if result.signal_key in self._signal_keys:
            return []  # duplicate prevention
        self._signal_keys.add(result.signal_key)

        now = datetime.now(timezone.utc)
        allocs = list(self.config.tp_allocations)
        # Match allocation length to TP count
        tps = list(result.take_profits)
        if len(allocs) < len(tps):
            # pad remaining equally on last
            rem = 1.0 - sum(allocs)
            extra = len(tps) - len(allocs)
            allocs = list(allocs) + [rem / extra] * extra
        elif len(allocs) > len(tps):
            allocs = list(allocs[: len(tps)])
            s = sum(allocs)
            allocs = [a / s for a in allocs]

        trade = SimulatedTrade(
            trade_id=new_trade_id(
                replay_session_id=self.session_id,
                signal_key=result.signal_key,
                decision_event_index=event_index,
                direction=str(result.direction),
            ),
            signal_key=result.signal_key,
            replay_session_id=self.session_id,
            signal_id=snap.decision_id,
            exchange=snap.exchange,
            symbol=snap.symbol,
            market_type=snap.market_type,
            direction=result.direction,
            decision=str(snap.decision),
            decision_timestamp=ensure_utc(snap.replay_timestamp),
            decision_event_index=event_index,
            lifecycle_status="pending_entry",
            entry_zone=snap.entry_zone,
            entry_limit_price=result.entry_limit_price,
            initial_stop_loss=result.stop_loss or 0.0,
            current_stop_loss=result.stop_loss or 0.0,
            take_profit_levels=tps,
            tp_allocations=allocs,
            tp_filled=[False] * len(tps),
            original_quantity=result.quantity or 0.0,
            remaining_quantity=result.quantity or 0.0,
            expires_at=result.expires_at,
            risk_reward=snap.risk_reward,
            decision_reason=snap.decision_reason,
            config_version=self.config.config_version,
            created_at=now,
            updated_at=now,
        )
        self.trades[trade.trade_id] = trade
        ev = append_event(
            trade,
            event_type="trade_pending",
            timestamp=trade.decision_timestamp,
            price=trade.entry_limit_price,
            quantity=trade.original_quantity,
            reason="Eligible historical signal — awaiting entry fill.",
        )
        return [ev]

    def _build_rejected(
        self,
        snap: HistoricalAnalysisSnapshot,
        reason: str,
    ) -> SimulatedTrade:
        now = datetime.now(timezone.utc)
        rej_direction = "LONG" if str(snap.decision).upper() == "LONG" else "SHORT"
        rej_key = f"rej|{snap.decision_id}|{snap.replay_timestamp.isoformat()}"
        return SimulatedTrade(
            trade_id=new_trade_id(
                replay_session_id=self.session_id,
                signal_key=rej_key,
                decision_event_index=snap.event_index,
                direction=rej_direction,
            ),
            signal_key=rej_key,
            replay_session_id=self.session_id,
            signal_id=snap.decision_id,
            exchange=snap.exchange,
            symbol=snap.symbol,
            market_type=snap.market_type,
            direction=rej_direction,
            decision=str(snap.decision),
            decision_timestamp=ensure_utc(snap.replay_timestamp),
            decision_event_index=snap.event_index,
            lifecycle_status="rejected",
            entry_zone=snap.entry_zone,
            initial_stop_loss=float(snap.stop_loss or 0.0),
            current_stop_loss=float(snap.stop_loss or 0.0),
            take_profit_levels=list(snap.take_profit_levels or []),
            original_quantity=float(snap.position_size or 0.0),
            remaining_quantity=0.0,
            rejection_reason=reason,
            config_version=self.config.config_version,
            created_at=now,
            updated_at=now,
        )

    def _process_pending_entries(
        self,
        candle: Candle,
        clock: datetime,
        series_by_tf: dict[Timeframe, list[Candle]],
    ) -> list[SimulationExecutionEvent]:
        events: list[SimulationExecutionEvent] = []
        tf = self.config.execution_timeframe
        for trade in list(self.trades.values()):
            if trade.lifecycle_status != "pending_entry":
                continue
            fill = try_fill_entry(
                direction=trade.direction,
                limit_price=trade.entry_limit_price or 0.0,
                stop_loss=trade.current_stop_loss,
                take_profits=[
                    p
                    for i, p in enumerate(trade.take_profit_levels)
                    if not trade.tp_filled[i]
                ],
                candle=candle,
                timeframe=tf,
                decision_timestamp=trade.decision_timestamp,
                expires_at=trade.expires_at,
                clock=clock,
            )
            if fill.expired:
                trade.lifecycle_status = "cancelled"
                trade.exit_timestamp = clock
                trade.remaining_quantity = 0.0
                events.append(
                    append_event(
                        trade,
                        event_type="trade_cancelled",
                        timestamp=clock,
                        reason=fill.reason or "Entry expired.",
                    )
                )
                continue
            if not fill.filled or fill.fill_price is None:
                continue

            # Entry + SL / TP same candle ambiguity
            if fill.ambiguous_with_sl or fill.ambiguous_with_tp:
                policy = self.config.ambiguity_policy
                if policy == "mark_ambiguous" and fill.ambiguous_with_sl:
                    trade.lifecycle_status = "ambiguous_execution"
                    trade.entry_price = fill.fill_price
                    trade.entry_timestamp = fill.fill_timestamp
                    trade.executed_quantity = trade.original_quantity
                    trade.remaining_quantity = 0.0
                    trade.ambiguity_warnings.append(
                        "Entry and SL touched in the same candle; marked ambiguous."
                    )
                    events.append(
                        append_event(
                            trade,
                            event_type="trade_ambiguous",
                            timestamp=fill.fill_timestamp or clock,
                            price=fill.fill_price,
                            quantity=trade.original_quantity,
                            reason=trade.ambiguity_warnings[-1],
                            ambiguity_policy_applied=policy,
                            candle_open_time=fill.candle_open_time,
                        )
                    )
                    continue
                if fill.ambiguous_with_sl and policy == "conservative_stop_first":
                    # Fill then immediately stop — adverse path
                    trade.entry_price = fill.fill_price
                    trade.entry_timestamp = fill.fill_timestamp
                    trade.executed_quantity = trade.original_quantity
                    trade.lifecycle_status = "open"
                    events.append(
                        append_event(
                            trade,
                            event_type="trade_opened",
                            timestamp=fill.fill_timestamp or clock,
                            price=fill.fill_price,
                            quantity=trade.original_quantity,
                            ambiguity_policy_applied=policy,
                            candle_open_time=fill.candle_open_time,
                            reason="Entry filled; same-candle SL will apply conservatively.",
                        )
                    )
                    # Apply SL on same candle
                    events.extend(self._apply_sl(trade, candle, clock, policy))
                    continue

            trade.entry_price = fill.fill_price
            trade.entry_timestamp = fill.fill_timestamp
            trade.executed_quantity = trade.original_quantity
            trade.lifecycle_status = "open"
            events.append(
                append_event(
                    trade,
                    event_type="trade_opened",
                    timestamp=fill.fill_timestamp or clock,
                    price=fill.fill_price,
                    quantity=trade.original_quantity,
                    candle_open_time=fill.candle_open_time,
                    reason="Limit entry filled.",
                )
            )
            # If TP also touched same candle without SL, process exits
            if fill.ambiguous_with_tp and not fill.ambiguous_with_sl:
                events.extend(
                    self._process_exits_for_trade(trade, candle, clock, series_by_tf)
                )
        return events

    def _process_open_exits(
        self,
        candle: Candle,
        clock: datetime,
        series_by_tf: dict[Timeframe, list[Candle]],
    ) -> list[SimulationExecutionEvent]:
        events: list[SimulationExecutionEvent] = []
        for trade in list(self.trades.values()):
            if trade.lifecycle_status not in {"open", "partially_closed"}:
                continue
            # Only candles after entry
            if trade.entry_timestamp is None:
                continue
            if candle_close_time(candle, self.config.execution_timeframe) <= ensure_utc(
                trade.entry_timestamp
            ):
                # Allow same candle as entry only if already handled in entry path;
                # subsequent processing uses close > entry timestamp.
                # If entry filled on this candle, entry_timestamp == close_t — skip reprocess
                if candle_close_time(
                    candle, self.config.execution_timeframe
                ) == ensure_utc(trade.entry_timestamp):
                    continue
                continue
            events.extend(
                self._process_exits_for_trade(trade, candle, clock, series_by_tf)
            )
        return events

    def _process_exits_for_trade(
        self,
        trade: SimulatedTrade,
        candle: Candle,
        clock: datetime,
        series_by_tf: dict[Timeframe, list[Candle]],
    ) -> list[SimulationExecutionEvent]:
        pending_tps = [
            (i, p)
            for i, p in enumerate(trade.take_profit_levels)
            if not trade.tp_filled[i]
        ]
        lower = None
        if self.config.ambiguity_policy == "use_lower_timeframe_if_available":
            lower = series_by_tf.get(self.config.lower_timeframe, [])

        result = resolve_same_candle_order(
            direction=trade.direction,
            candle=candle,
            stop=trade.current_stop_loss,
            pending_tps=pending_tps,
            policy=self.config.ambiguity_policy,
            lower_tf_candles=lower,
            lower_tf=self.config.lower_timeframe,
        )
        events: list[SimulationExecutionEvent] = []
        if result.ambiguity_warning:
            trade.ambiguity_warnings.append(result.ambiguity_warning)

        for hit in result.hits:
            if hit.kind == "sl":
                events.extend(
                    self._apply_sl(
                        trade,
                        candle,
                        clock,
                        result.policy_applied,
                        fill_price=hit.price,
                        mark_ambiguous=result.ambiguous,
                    )
                )
                break
            if hit.kind == "tp" and hit.tp_index is not None:
                events.extend(
                    self._apply_tp(
                        trade,
                        tp_index=hit.tp_index,
                        price=hit.price,
                        timestamp=result.candle_close_time or clock,
                        policy=result.policy_applied,
                        ambiguous=result.ambiguous,
                    )
                )
        try:
            assert_quantities(trade, tol=self.config.quantity_tolerance)
        except AssertionError as exc:
            logger.error("%s", exc)
        return events

    def _apply_sl(
        self,
        trade: SimulatedTrade,
        candle: Candle,
        clock: datetime,
        policy: str | None,
        fill_price: float | None = None,
        mark_ambiguous: bool = False,
    ) -> list[SimulationExecutionEvent]:
        if trade.remaining_quantity <= self.config.quantity_tolerance:
            return []
        qty = trade.remaining_quantity
        price = fill_price
        if price is None:
            from app.replay.simulation.exit_execution import _sl_fill_price

            price = _sl_fill_price(trade.direction, candle, trade.current_stop_loss)
        trade.quantity_closed_sl += qty
        trade.remaining_quantity = 0.0
        trade.exit_timestamp = clock
        if mark_ambiguous:
            trade.lifecycle_status = "ambiguous_execution"
            et: str = "trade_ambiguous"
        else:
            trade.lifecycle_status = "closed_sl"
            et = "trade_closed"
        return [
            append_event(
                trade,
                event_type=et,  # type: ignore[arg-type]
                timestamp=clock,
                price=price,
                quantity=qty,
                reason="Stop loss filled.",
                ambiguity_policy_applied=policy,
                candle_open_time=ensure_utc(candle.timestamp),
            )
        ]

    def _apply_tp(
        self,
        trade: SimulatedTrade,
        *,
        tp_index: int,
        price: float,
        timestamp: datetime,
        policy: str | None,
        ambiguous: bool,
    ) -> list[SimulationExecutionEvent]:
        if trade.tp_filled[tp_index]:
            return []
        if trade.remaining_quantity <= self.config.quantity_tolerance:
            return []
        alloc = trade.tp_allocations[tp_index] if tp_index < len(trade.tp_allocations) else 0.0
        # Quantity for this TP based on original, but capped by remaining
        target_qty = trade.original_quantity * alloc
        # Adjust last TP to clear remainder
        remaining_unfilled = [
            i for i, filled in enumerate(trade.tp_filled) if not filled
        ]
        if remaining_unfilled and remaining_unfilled[-1] == tp_index:
            qty = trade.remaining_quantity
        else:
            qty = min(trade.remaining_quantity, target_qty)

        if qty <= self.config.quantity_tolerance:
            return []

        trade.tp_filled[tp_index] = True
        trade.remaining_quantity = max(0.0, trade.remaining_quantity - qty)
        trade.quantity_closed_tp += qty

        events: list[SimulationExecutionEvent] = []
        if trade.remaining_quantity <= self.config.quantity_tolerance:
            trade.remaining_quantity = 0.0
            trade.lifecycle_status = "closed_tp"
            trade.exit_timestamp = timestamp
            events.append(
                append_event(
                    trade,
                    event_type="trade_closed",
                    timestamp=timestamp,
                    price=price,
                    quantity=qty,
                    tp_index=tp_index,
                    reason=f"TP{tp_index + 1} final close.",
                    ambiguity_policy_applied=policy,
                )
            )
        else:
            trade.lifecycle_status = "partially_closed"
            events.append(
                append_event(
                    trade,
                    event_type="trade_partially_closed",
                    timestamp=timestamp,
                    price=price,
                    quantity=qty,
                    tp_index=tp_index,
                    reason=f"TP{tp_index + 1} partial close.",
                    ambiguity_policy_applied=policy,
                )
            )
        if ambiguous:
            trade.ambiguity_warnings.append(
                f"Ambiguous path around TP{tp_index + 1} on same candle."
            )
        return events

    def _expire_pending(self, clock: datetime) -> list[SimulationExecutionEvent]:
        events: list[SimulationExecutionEvent] = []
        for trade in list(self.trades.values()):
            if trade.lifecycle_status != "pending_entry":
                continue
            if trade.expires_at is None:
                continue
            if clock > ensure_utc(trade.expires_at):
                trade.lifecycle_status = "cancelled"
                trade.exit_timestamp = clock
                trade.remaining_quantity = 0.0
                events.append(
                    append_event(
                        trade,
                        event_type="trade_cancelled",
                        timestamp=clock,
                        reason="Entry not filled before setup expiration.",
                    )
                )
        return events
