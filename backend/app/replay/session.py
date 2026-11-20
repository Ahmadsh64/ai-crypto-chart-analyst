"""In-memory replay session controller (Phase 5.1)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.replay.config import (
    DEFAULT_REPLAY_CONFIG,
    SPEED_DELAY_SECONDS,
    ReplayConfig,
    ReplaySpeed,
    ReplayStatus,
)
from app.replay.analysis.config import (
    DEFAULT_HISTORICAL_ANALYSIS_CONFIG,
    HistoricalAnalysisConfig,
)
from app.replay.analysis.models import HistoricalAnalysisSnapshot
from app.replay.analysis.pipeline import run_historical_analysis
from app.replay.analysis.snapshot import snapshot_ws_payload
from app.replay.data_loader import load_replay_series
from app.replay.models import CandleGapInfo, ReplaySessionInfo, ReplaySnapshot
from app.replay.analytics.config import DEFAULT_ANALYTICS_CONFIG, AnalyticsConfig
from app.replay.analytics.engine import AnalyticsEngine
from app.replay.analytics.trade_filter import AnalyticsFilter
from app.replay.costs.config import DEFAULT_COST_CONFIG, ExecutionCostConfig
from app.replay.costs.engine import CostEngine
from app.replay.simulation.config import DEFAULT_SIMULATION_CONFIG, SimulationConfig
from app.replay.simulation.simulator import TradeSimulator
from app.replay.timeline import (
    build_event_timeline,
    candle_close_time,
    ensure_utc,
    snapshot_at,
)

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[str, dict], Awaitable[None]]


class ReplaySession:
    def __init__(
        self,
        *,
        exchange: ExchangeId,
        symbol: str,
        market_type: MarketType,
        start_time: datetime,
        end_time: datetime,
        timeframes: tuple[Timeframe, ...] | None = None,
        config: ReplayConfig | None = None,
        on_event: BroadcastFn | None = None,
    ) -> None:
        self.session_id = "rp_" + uuid.uuid4().hex[:16]
        self.exchange = exchange
        self.symbol = symbol.upper()
        self.market_type = market_type
        self.start_time = start_time
        self.end_time = end_time
        self.config = config or DEFAULT_REPLAY_CONFIG
        self.timeframes = timeframes or self.config.timeframes
        self.speed: ReplaySpeed = self.config.default_speed
        self.status: ReplayStatus = "created"
        self.created_at = datetime.now(timezone.utc)
        self.error: str | None = None
        self.event_index = 0
        self.event_times: list[datetime] = []
        self.series_by_tf: dict[Timeframe, list[Candle]] = {}
        self.gaps: list[CandleGapInfo] = []
        self.limitations: list[str] = []
        self._on_event = on_event
        self._runner: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        # Phase 5.2.1 historical analysis
        self.analysis_enabled: bool = False
        self.analysis_config: HistoricalAnalysisConfig = DEFAULT_HISTORICAL_ANALYSIS_CONFIG
        self.current_analysis: HistoricalAnalysisSnapshot | None = None
        self._analysis_by_index: dict[int, HistoricalAnalysisSnapshot] = {}
        self._analysis_ordered: list[HistoricalAnalysisSnapshot] = []
        # Phase 5.2.2 trade simulation
        self.simulation_config: SimulationConfig = DEFAULT_SIMULATION_CONFIG
        self.simulator = TradeSimulator(
            session_id=self.session_id,
            config=self.simulation_config,
        )
        self._simulation_last_index: int | None = None
        # Phase 5.2.3 execution costs
        self.cost_config: ExecutionCostConfig = DEFAULT_COST_CONFIG.model_copy(deep=True)
        self.cost_engine = CostEngine(
            session_id=self.session_id,
            config=self.cost_config,
        )
        # Phase 5.2.4 performance analytics
        self.analytics_config: AnalyticsConfig = DEFAULT_ANALYTICS_CONFIG.model_copy(
            deep=True
        )
        self.analytics_engine = AnalyticsEngine(
            session_id=self.session_id,
            config=self.analytics_config,
        )
        self.analytics_filter = AnalyticsFilter()

    async def load(self) -> ReplaySnapshot:
        self.status = "loading"
        await self._emit("replay_started", {"phase": "loading"})
        try:
            series, gaps, limitations = await load_replay_series(
                exchange=self.exchange,
                symbol=self.symbol,
                market_type=self.market_type,
                start=self.start_time,
                end=self.end_time,
                timeframes=self.timeframes,
                config=self.config,
            )
            self.series_by_tf = series
            self.gaps = gaps
            self.limitations = limitations
            self.event_times = build_event_timeline(
                series,
                start=self.start_time,
                end=self.end_time,
                config=self.config,
            )
            self.event_index = 0
            if not self.event_times:
                self.status = "error"
                self.error = "No replay events in range (insufficient historical data)."
                self.limitations.append(self.error)
            else:
                self.status = "ready"
            snap = self.current_snapshot()
            await self._emit("replay_snapshot", {"snapshot": snap.model_dump(mode="json")})
            return snap
        except Exception as exc:  # noqa: BLE001
            self.status = "error"
            self.error = str(exc)
            logger.exception("Replay load failed: %s", exc)
            await self._emit("replay_error", {"error": str(exc)})
            raise

    def info(self) -> ReplaySessionInfo:
        ts = self.event_times[self.event_index] if self.event_times else None
        return ReplaySessionInfo(
            session_id=self.session_id,
            exchange=self.exchange,
            symbol=self.symbol,
            market_type=self.market_type,
            start_time=self.start_time,
            end_time=self.end_time,
            timeframes=list(self.timeframes),
            status=self.status,
            speed=self.speed,
            event_index=self.event_index,
            event_count=len(self.event_times),
            replay_timestamp=ts,
            created_at=self.created_at,
            error=self.error,
            config_version=self.config.config_version,
            data_quality=self.current_snapshot().data_quality if self.event_times or self.status == "error" else "empty",
            limitations=self.limitations,
        )

    def current_snapshot(self) -> ReplaySnapshot:
        return snapshot_at(
            session_id=self.session_id,
            exchange=self.exchange,
            symbol=self.symbol,
            market_type=self.market_type,
            series_by_tf=self.series_by_tf,
            gaps=self.gaps,
            limitations=self.limitations,
            event_times=self.event_times,
            event_index=self.event_index,
            status=self.status,
            speed=self.speed,
            config=self.config,
        )

    async def start(self) -> ReplaySnapshot:
        async with self._lock:
            if self.status in {"created", "loading", "error"}:
                raise RuntimeError("Session is not ready to start.")
            if self.status == "completed":
                self.event_index = 0
            self.status = "running"
            await self._emit("replay_started", {"speed": self.speed})
            self._ensure_runner()
            return self.current_snapshot()

    async def pause(self) -> ReplaySnapshot:
        async with self._lock:
            if self.status == "running":
                self.status = "paused"
                await self._emit("replay_paused", {})
            return self.current_snapshot()

    async def resume(self) -> ReplaySnapshot:
        async with self._lock:
            if self.status == "paused":
                self.status = "running"
                await self._emit("replay_resumed", {"speed": self.speed})
                self._ensure_runner()
            return self.current_snapshot()

    async def stop(self) -> ReplaySnapshot:
        async with self._lock:
            self.status = "stopped"
            await self._cancel_runner()
            await self._emit("replay_stopped", {})
            return self.current_snapshot()

    async def reset(self) -> ReplaySnapshot:
        async with self._lock:
            await self._cancel_runner()
            self.event_index = 0
            self.status = "ready" if self.event_times else "error"
            # Keep immutable analysis history; refresh current pointer to index 0 cache.
            self.current_analysis = self._analysis_by_index.get(0)
            # Simulation rebuilds from scratch (deterministic).
            sim_was_enabled = self.simulator.enabled
            cost_was_enabled = self.cost_engine.enabled
            self.simulator.reset()
            self._simulation_last_index = None
            self.cost_engine.reset()
            analytics_was_enabled = self.analytics_engine.enabled
            self.analytics_engine.reset()
            if sim_was_enabled:
                self.simulator.enable()
            if cost_was_enabled:
                self.cost_engine.enable()
            if analytics_was_enabled:
                self.analytics_engine.enable()
            snap = self.current_snapshot()
            await self._emit("replay_reset", {"snapshot": snap.model_dump(mode="json")})
            if self.analysis_enabled:
                await self._run_analysis_unlocked(emit=True)
            elif sim_was_enabled:
                await self._run_simulation_unlocked(analysis=self.current_analysis)
            if cost_was_enabled:
                await self._rebuild_costs_unlocked(emit=True)
            if analytics_was_enabled:
                await self._rebuild_analytics_unlocked(emit=True)
            return snap

    async def step(self) -> ReplaySnapshot:
        async with self._lock:
            if self.status == "running":
                self.status = "paused"
                await self._cancel_runner()
            if not self.event_times:
                raise RuntimeError("No events to step.")
            if self.event_index >= len(self.event_times) - 1:
                self.status = "completed"
                await self._emit("replay_completed", {})
                return self.current_snapshot()
            prev = self.event_index
            self.event_index += 1
            snap = self.current_snapshot()
            await self._emit_step_events(prev, snap)
            if self.event_index >= len(self.event_times) - 1:
                self.status = "completed"
                await self._emit("replay_completed", {})
            else:
                self.status = "paused"
            return self.current_snapshot()

    async def set_speed(self, speed: ReplaySpeed) -> ReplaySnapshot:
        async with self._lock:
            self.speed = speed
            return self.current_snapshot()

    async def seek(self, event_index: int) -> ReplaySnapshot:
        """Deterministic jump to an event index (instant / tests). No look-ahead."""
        async with self._lock:
            if not self.event_times:
                raise RuntimeError("No events loaded.")
            self.event_index = max(0, min(int(event_index), len(self.event_times) - 1))
            if self.event_index >= len(self.event_times) - 1:
                self.status = "completed"
            elif self.status not in {"running", "paused", "ready", "stopped"}:
                self.status = "paused"
            # Costs/analytics require a rebuilt trade prefix at the seek clock.
            # Re-enable simulation when those layers are on (matches enable_costs).
            need_sim_stack = (
                self.simulator.enabled
                or self.cost_engine.enabled
                or self.analytics_engine.enabled
            )
            if need_sim_stack:
                if not self.analysis_enabled:
                    self.analysis_enabled = True
                if not self.simulator.enabled:
                    self.simulator.enable()
                await self._rebuild_simulation_unlocked(emit=True)
            elif self.analysis_enabled:
                await self._run_analysis_unlocked(emit=True)
            return self.current_snapshot()

    async def enable_analysis(self) -> HistoricalAnalysisSnapshot | None:
        async with self._lock:
            self.analysis_enabled = True
            return await self._run_analysis_unlocked(emit=True)

    async def disable_analysis(self) -> None:
        async with self._lock:
            self.analysis_enabled = False

    async def enable_simulation(self):
        async with self._lock:
            # Simulation consumes analysis snapshots — enable analysis if needed.
            if not self.analysis_enabled:
                self.analysis_enabled = True
            self.simulator.enable()
            await self._emit(
                "simulation_enabled",
                {"disclaimer": self.simulation_config.disclaimer},
            )
            analysis = self.current_analysis
            if analysis is None:
                analysis = await self._run_analysis_unlocked(emit=True)
            else:
                await self._run_simulation_unlocked(analysis=analysis)
            return self.simulator.snapshot(
                self.event_times[self.event_index] if self.event_times else None
            )

    async def disable_simulation(self):
        async with self._lock:
            self.simulator.disable()
            await self._emit("simulation_disabled", {})
            return self.simulator.snapshot(
                self.event_times[self.event_index] if self.event_times else None
            )

    async def reset_simulation(self):
        async with self._lock:
            enabled = self.simulator.enabled
            cost_enabled = self.cost_engine.enabled
            self.simulator.reset()
            self._simulation_last_index = None
            self.cost_engine.reset()
            if enabled:
                self.simulator.enable()
                await self._run_simulation_unlocked(analysis=self.current_analysis)
            if cost_enabled:
                self.cost_engine.enable()
                await self._rebuild_costs_unlocked(emit=True)
            await self._emit(
                "simulation_snapshot",
                self.simulator.snapshot(
                    self.event_times[self.event_index] if self.event_times else None
                ).model_dump(mode="json"),
            )
            return self.simulator.snapshot(
                self.event_times[self.event_index] if self.event_times else None
            )

    async def enable_costs(self):
        async with self._lock:
            # Costs consume simulation fills — ensure analysis + simulation are on.
            if not self.analysis_enabled:
                self.analysis_enabled = True
            if not self.simulator.enabled:
                self.simulator.enable()
                await self._emit(
                    "simulation_enabled",
                    {"disclaimer": self.simulation_config.disclaimer},
                )
                analysis = self.current_analysis
                if analysis is None:
                    analysis = await self._run_analysis_unlocked(emit=True)
                else:
                    await self._run_simulation_unlocked(analysis=analysis)
            self.cost_engine.enable()
            await self._emit(
                "cost_model_enabled",
                {
                    "disclaimer": self.cost_config.disclaimer,
                    "config": self.cost_config.snapshot(),
                },
            )
            await self._rebuild_costs_unlocked(emit=True)
            return self.cost_engine.snapshot(
                list(self.simulator.trades.values()),
                replay_timestamp=(
                    self.event_times[self.event_index] if self.event_times else None
                ),
            )

    async def disable_costs(self):
        async with self._lock:
            self.cost_engine.disable()
            await self._emit("cost_model_disabled", {})
            return self.cost_engine.snapshot(
                list(self.simulator.trades.values()),
                replay_timestamp=(
                    self.event_times[self.event_index] if self.event_times else None
                ),
            )

    async def update_cost_config(self, config: ExecutionCostConfig):
        """Update cost config and rebuild ledger (fills unchanged)."""
        async with self._lock:
            enabled = self.cost_engine.enabled
            self.cost_config = config
            self.cost_engine.update_config(config)
            if enabled:
                self.cost_engine.enable()
                await self._rebuild_costs_unlocked(emit=True)
            return self.cost_engine.snapshot(
                list(self.simulator.trades.values()),
                replay_timestamp=(
                    self.event_times[self.event_index] if self.event_times else None
                ),
            )

    async def reset_costs(self):
        async with self._lock:
            enabled = self.cost_engine.enabled
            self.cost_engine.reset()
            if enabled:
                self.cost_engine.enable()
                await self._rebuild_costs_unlocked(emit=True)
            return self.cost_engine.snapshot(
                list(self.simulator.trades.values()),
                replay_timestamp=(
                    self.event_times[self.event_index] if self.event_times else None
                ),
            )

    async def enable_analytics(self):
        async with self._lock:
            # Analytics consume cost results — enable costs (+ sim + analysis) first.
            if not self.cost_engine.enabled:
                # Inline enable_costs path without re-entering lock.
                if not self.analysis_enabled:
                    self.analysis_enabled = True
                if not self.simulator.enabled:
                    self.simulator.enable()
                    await self._emit(
                        "simulation_enabled",
                        {"disclaimer": self.simulation_config.disclaimer},
                    )
                    analysis = self.current_analysis
                    if analysis is None:
                        analysis = await self._run_analysis_unlocked(emit=True)
                    else:
                        await self._run_simulation_unlocked(analysis=analysis)
                self.cost_engine.enable()
                await self._emit(
                    "cost_model_enabled",
                    {
                        "disclaimer": self.cost_config.disclaimer,
                        "config": self.cost_config.snapshot(),
                    },
                )
                await self._rebuild_costs_unlocked(emit=True)
            self.analytics_engine.enable()
            await self._emit(
                "analytics_enabled",
                {
                    "disclaimer": self.analytics_config.disclaimer,
                    "config": self.analytics_config.snapshot(),
                },
            )
            return await self._rebuild_analytics_unlocked(emit=True)

    async def disable_analytics(self):
        async with self._lock:
            self.analytics_engine.disable()
            await self._emit("analytics_disabled", {})
            return self.analytics_engine.snapshot(
                list(self.simulator.trades.values()),
                self.cost_engine,
                replay_timestamp=(
                    self.event_times[self.event_index] if self.event_times else None
                ),
                event_index=self.event_index,
                filt=self.analytics_filter,
            )

    async def update_analytics_config(self, config: AnalyticsConfig):
        async with self._lock:
            enabled = self.analytics_engine.enabled
            self.analytics_config = config
            self.analytics_engine.update_config(config)
            if enabled:
                self.analytics_engine.enable()
                return await self._rebuild_analytics_unlocked(emit=True)
            return self.analytics_engine.snapshot(
                list(self.simulator.trades.values()),
                self.cost_engine,
                replay_timestamp=(
                    self.event_times[self.event_index] if self.event_times else None
                ),
                event_index=self.event_index,
                filt=self.analytics_filter,
            )

    async def set_analytics_filter(self, filt: AnalyticsFilter):
        async with self._lock:
            self.analytics_filter = filt
            self.analytics_engine.reset()
            if self.analytics_engine.enabled:
                return await self._rebuild_analytics_unlocked(emit=True)
            return self.analytics_engine.snapshot(
                list(self.simulator.trades.values()),
                self.cost_engine,
                replay_timestamp=(
                    self.event_times[self.event_index] if self.event_times else None
                ),
                event_index=self.event_index,
                filt=self.analytics_filter,
            )

    def get_analysis(self) -> HistoricalAnalysisSnapshot | None:
        return self.current_analysis

    def get_analysis_at(self, timestamp: datetime) -> HistoricalAnalysisSnapshot | None:
        ts = ensure_utc(timestamp)
        for snap in self._analysis_ordered:
            if ensure_utc(snap.replay_timestamp) == ts:
                return snap
        # Exact match on event timeline
        for idx, et in enumerate(self.event_times):
            if ensure_utc(et) == ts:
                return self._analysis_by_index.get(idx)
        return None

    def list_analysis_history(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> tuple[list[HistoricalAnalysisSnapshot], int]:
        items = list(self._analysis_ordered)
        if start_time is not None:
            st = ensure_utc(start_time)
            items = [s for s in items if ensure_utc(s.replay_timestamp) >= st]
        if end_time is not None:
            et = ensure_utc(end_time)
            items = [s for s in items if ensure_utc(s.replay_timestamp) <= et]
        total = len(items)
        offset = max(0, offset)
        limit = max(1, min(limit, 500))
        return items[offset : offset + limit], total

    def _ensure_runner(self) -> None:
        if self._runner is None or self._runner.done():
            self._runner = asyncio.create_task(self._run_loop(), name=f"replay-{self.session_id}")

    async def _cancel_runner(self) -> None:
        if self._runner and not self._runner.done():
            self._runner.cancel()
            try:
                await self._runner
            except asyncio.CancelledError:
                pass
        self._runner = None

    async def _run_loop(self) -> None:
        try:
            while self.status == "running":
                if not self.event_times:
                    self.status = "error"
                    break
                if self.event_index >= len(self.event_times) - 1:
                    self.status = "completed"
                    await self._emit("replay_completed", {})
                    break
                delay = SPEED_DELAY_SECONDS.get(self.speed, 0.0)
                if delay > 0:
                    await asyncio.sleep(delay)
                if self.status != "running":
                    break
                prev = self.event_index
                self.event_index += 1
                snap = self.current_snapshot()
                await self._emit_step_events(prev, snap)
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            self.status = "error"
            self.error = str(exc)
            await self._emit("replay_error", {"error": str(exc)})

    async def _emit_step_events(self, prev_index: int, snap: ReplaySnapshot) -> None:
        await self._emit(
            "replay_snapshot",
            {"snapshot": snap.model_dump(mode="json")},
        )
        # Emit closed candle updates for TFs that newly closed at this clock
        clock = snap.replay_timestamp
        for tf in self.timeframes:
            series = self.series_by_tf.get(tf, [])
            from app.replay.timeline import candle_close_time

            newly = [
                c
                for c in series
                if candle_close_time(c, tf) == clock
            ]
            for c in newly:
                await self._emit(
                    "replay_candle_closed",
                    {
                        "timeframe": tf.value,
                        "candle": c.model_dump(mode="json"),
                    },
                    timeframe=tf,
                )
            state = snap.timeframes.get(tf.value)
            if state and state.forming_candle is not None:
                await self._emit(
                    "replay_candle_update",
                    {
                        "timeframe": tf.value,
                        "candle": state.forming_candle.model_dump(mode="json"),
                        "is_closed": False,
                    },
                    timeframe=tf,
                )
        if self.analysis_enabled:
            await self._run_analysis_unlocked(emit=True)
        elif self.simulator.enabled:
            await self._run_simulation_unlocked(analysis=self.current_analysis)

    async def _run_analysis_unlocked(
        self,
        *,
        emit: bool,
    ) -> HistoricalAnalysisSnapshot | None:
        """Run or reuse cached analysis for the current event index. Caller holds lock."""
        if not self.event_times:
            self.current_analysis = None
            return None
        idx = self.event_index
        if self.analysis_config.enable_cache and idx in self._analysis_by_index:
            snap = self._analysis_by_index[idx]
            self.current_analysis = snap
            if emit:
                await self._emit(
                    "replay_analysis_update",
                    snapshot_ws_payload(snap),
                )
            await self._run_simulation_unlocked(analysis=snap, emit=emit)
            return snap

        clock = self.event_times[idx]
        try:
            # CPU-bound pipeline — offload to thread so the event loop stays responsive.
            snap = await asyncio.to_thread(
                run_historical_analysis,
                session_id=self.session_id,
                exchange=self.exchange,
                symbol=self.symbol,
                market_type=self.market_type,
                series_by_tf=self.series_by_tf,
                clock=clock,
                event_index=idx,
                config=self.analysis_config,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Historical analysis failed: %s", exc)
            await self._emit(
                "replay_analysis_error",
                {"error": str(exc), "event_index": idx},
            )
            return self.current_analysis

        # Immutable: do not overwrite an earlier snapshot for this index.
        if idx not in self._analysis_by_index:
            self._analysis_by_index[idx] = snap
            self._analysis_ordered.append(snap)
            # Bound memory
            max_h = self.analysis_config.max_history
            while len(self._analysis_ordered) > max_h:
                dropped = self._analysis_ordered.pop(0)
                # Only drop cache entry if it matches the dropped snapshot index
                cached = self._analysis_by_index.get(dropped.event_index)
                if cached is dropped:
                    self._analysis_by_index.pop(dropped.event_index, None)
        else:
            snap = self._analysis_by_index[idx]

        self.current_analysis = snap
        if emit:
            await self._emit(
                "replay_analysis_update",
                snapshot_ws_payload(snap),
            )
        await self._run_simulation_unlocked(analysis=snap, emit=emit)
        return snap

    async def _rebuild_simulation_unlocked(self, *, emit: bool) -> None:
        """Deterministically rebuild simulation from event 0..current index."""
        if not self.simulator.enabled or not self.event_times:
            return
        enabled = self.simulator.enabled
        self.simulator.reset()
        if enabled:
            self.simulator.enable()
        self._simulation_last_index = None
        saved_idx = self.event_index
        # Temporarily disable nested simulation from analysis; drive ticks here.
        for i in range(saved_idx + 1):
            self.event_index = i
            analysis = self._analysis_by_index.get(i)
            if analysis is None and self.analysis_enabled:
                # Populate analysis cache without nested simulation emit/process.
                prev_enabled = self.simulator.enabled
                self.simulator.enabled = False
                try:
                    analysis = await self._run_analysis_unlocked(emit=False)
                finally:
                    self.simulator.enabled = prev_enabled
            elif analysis is not None:
                self.current_analysis = analysis
            await self._run_simulation_unlocked(analysis=analysis, emit=False)
        self.event_index = saved_idx
        # Cache-only rebuilds must still point current_analysis at the seek target.
        if saved_idx in self._analysis_by_index:
            self.current_analysis = self._analysis_by_index[saved_idx]
        if emit:
            clock = self.event_times[saved_idx]
            await self._emit(
                "simulation_snapshot",
                self.simulator.snapshot(clock).model_dump(mode="json"),
            )
        if self.cost_engine.enabled:
            await self._rebuild_costs_unlocked(emit=emit)

    async def _rebuild_costs_unlocked(self, *, emit: bool) -> None:
        """Rebuild cost ledger from current simulated trades. Caller holds lock."""
        if not self.cost_engine.enabled:
            return
        try:
            entries = self.cost_engine.rebuild_from_trades(
                list(self.simulator.trades.values())
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Cost engine rebuild failed: %s", exc)
            if emit:
                await self._emit("cost_model_error", {"error": str(exc)})
            return
        if not emit:
            return
        clock = self.event_times[self.event_index] if self.event_times else None
        snap = self.cost_engine.snapshot(
            list(self.simulator.trades.values()),
            replay_timestamp=clock,
        )
        await self._emit(
            "execution_cost_update",
            snap.model_dump(mode="json"),
        )
        if entries:
            await self._emit(
                "execution_ledger_update",
                {
                    "count": len(entries),
                    "entries": [e.model_dump(mode="json") for e in entries[-20:]],
                },
            )
            await self._emit(
                "trade_pnl_update",
                {
                    "summary": snap.summary.model_dump(mode="json"),
                    "trades": [t.model_dump(mode="json") for t in snap.trades],
                },
            )
        if self.analytics_engine.enabled:
            await self._rebuild_analytics_unlocked(emit=emit)

    async def _rebuild_analytics_unlocked(self, *, emit: bool):
        """Rebuild analytics snapshot from current sim + cost state. Caller holds lock."""
        if not self.analytics_engine.enabled:
            return self.analytics_engine.snapshot(
                list(self.simulator.trades.values()),
                self.cost_engine,
                replay_timestamp=(
                    self.event_times[self.event_index] if self.event_times else None
                ),
                event_index=self.event_index,
                filt=self.analytics_filter,
            )
        self.analytics_engine.reset()
        try:
            snap = self.analytics_engine.compute(
                list(self.simulator.trades.values()),
                self.cost_engine,
                replay_timestamp=(
                    self.event_times[self.event_index] if self.event_times else None
                ),
                event_index=self.event_index,
                filt=self.analytics_filter,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Analytics engine failed: %s", exc)
            if emit:
                await self._emit("analytics_error", {"error": str(exc)})
            return None
        if emit:
            await self._emit(
                "analytics_summary_update",
                snap.summary.model_dump(mode="json"),
            )
            await self._emit(
                "analytics_equity_update",
                {
                    "completed": snap.equity_completed.model_dump(mode="json"),
                    "cashflow": snap.equity_cashflow.model_dump(mode="json"),
                },
            )
            await self._emit(
                "analytics_drawdown_update",
                snap.drawdown.model_dump(mode="json"),
            )
            await self._emit(
                "analytics_group_update",
                snap.groups.model_dump(mode="json"),
            )
        return snap

    async def _run_costs_unlocked(self, *, emit: bool) -> None:
        """Process new simulation fills into the cost ledger."""
        if not self.cost_engine.enabled:
            return
        try:
            entries = self.cost_engine.process_trades(
                list(self.simulator.trades.values())
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Cost engine failed: %s", exc)
            if emit:
                await self._emit("cost_model_error", {"error": str(exc)})
            return
        if not emit or not entries:
            return
        clock = self.event_times[self.event_index] if self.event_times else None
        snap = self.cost_engine.snapshot(
            list(self.simulator.trades.values()),
            replay_timestamp=clock,
        )
        await self._emit("execution_cost_update", snap.model_dump(mode="json"))
        await self._emit(
            "execution_ledger_update",
            {
                "count": len(entries),
                "entries": [e.model_dump(mode="json") for e in entries],
            },
        )
        await self._emit(
            "trade_pnl_update",
            {
                "summary": snap.summary.model_dump(mode="json"),
                "trades": [t.model_dump(mode="json") for t in snap.trades],
            },
        )
        if self.analytics_engine.enabled:
            await self._rebuild_analytics_unlocked(emit=True)

    async def _run_simulation_unlocked(
        self,
        *,
        analysis: HistoricalAnalysisSnapshot | None,
        emit: bool = True,
    ) -> None:
        """Process trade simulation for the current clock. Caller holds lock."""
        if not self.simulator.enabled or not self.event_times:
            return
        idx = self.event_index
        if self._simulation_last_index == idx:
            # Already processed this event index (avoid double fills).
            return
        clock = self.event_times[idx]
        tf = self.simulator.config.execution_timeframe
        series = self.series_by_tf.get(tf, [])
        exec_candle = next(
            (c for c in series if candle_close_time(c, tf) == clock),
            None,
        )
        try:
            events = self.simulator.process_tick(
                analysis=analysis,
                execution_candle=exec_candle,
                series_by_tf=self.series_by_tf,
                clock=clock,
                event_index=idx,
            )
            self._simulation_last_index = idx
        except Exception as exc:  # noqa: BLE001
            logger.exception("Trade simulation failed: %s", exc)
            if emit:
                await self._emit("simulation_error", {"error": str(exc)})
            return

        # Always feed fills into cost engine (idempotent); emit only when requested.
        await self._run_costs_unlocked(emit=emit)

        if not emit:
            return

        for ev in events:
            trade_id = None
            for t in self.simulator.trades.values():
                if any(e.event_id == ev.event_id for e in t.execution_events):
                    trade_id = t.trade_id
                    break
            await self._emit(
                ev.event_type,
                {
                    "trade_id": trade_id,
                    "event": ev.model_dump(mode="json"),
                },
            )
        await self._emit(
            "simulation_snapshot",
            self.simulator.snapshot(clock).model_dump(mode="json"),
        )

    async def _emit(
        self,
        event_type: str,
        payload: dict,
        timeframe: Timeframe | None = None,
    ) -> None:
        if self._on_event is None:
            return
        body = {
            "type": event_type,
            "session_id": self.session_id,
            "replay_timestamp": (
                self.event_times[self.event_index].isoformat()
                if self.event_times
                else None
            ),
            "exchange": self.exchange.value,
            "symbol": self.symbol,
            "market_type": self.market_type.value,
            "timeframe": timeframe.value if timeframe else None,
            "status": self.status,
            "payload": payload,
        }
        try:
            await self._on_event(event_type, body)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Replay broadcast failed: %s", exc)
