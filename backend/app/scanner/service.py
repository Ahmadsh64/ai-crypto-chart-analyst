"""Market opportunity scanner orchestration (Phase 5.5)."""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.core.logging import get_logger
from app.exchanges.types import ExchangeId
from app.scanner.analyze import analyze_candidate
from app.scanner.config import DEFAULT_SCANNER_CONFIG, ScannerConfig
from app.scanner.models import MarketOpportunity, ScanRunSummary
from app.scanner.ohlcv_cache import OhlcvTtlCache
from app.scanner.store import OpportunityStore, get_opportunity_store
from app.scanner.universe import discover_universe

logger = get_logger(__name__)


class MarketOpportunityScanner:
    def __init__(
        self,
        config: ScannerConfig | None = None,
        store: OpportunityStore | None = None,
    ) -> None:
        self.config = config or DEFAULT_SCANNER_CONFIG
        self.store = store or get_opportunity_store()
        self.cache = OhlcvTtlCache(self.config.ohlcv_cache_ttl_seconds)
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if not self.config.enabled or not self.config.auto_start:
            self.store.set_state("disabled", message="Scanner disabled")
            return
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="market-opportunity-scanner")
        logger.info("Market opportunity scanner started")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self.store.set_state("idle", message="Scanner stopped")

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_scan(trigger="scheduled")
            except Exception as exc:  # noqa: BLE001
                logger.exception("Scanner loop error: %s", exc)
                self.store.set_state("error", message=str(exc))
            next_at = datetime.now(timezone.utc) + timedelta(
                seconds=self.config.scan_interval_seconds
            )
            self.store.set_state(
                "idle",
                next_scan_at=next_at,
                scan_interval_seconds=self.config.scan_interval_seconds,
            )
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self.config.scan_interval_seconds,
                )
                break
            except TimeoutError:
                continue

    async def run_scan(self, *, trigger: str = "manual") -> ScanRunSummary:
        if self._lock.locked():
            summary = ScanRunSummary(
                scan_id=str(uuid.uuid4()),
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                status="skipped",
                errors=["Scan already in progress"],
                duration_seconds=0.0,
            )
            self.store.push_scan(summary)
            return summary

        async with self._lock:
            return await self._run_scan_locked(trigger=trigger)

    async def _run_scan_locked(self, *, trigger: str) -> ScanRunSummary:
        started = datetime.now(timezone.utc)
        scan_id = str(uuid.uuid4())
        summary = ScanRunSummary(
            scan_id=scan_id,
            started_at=started,
            status="running",
            exchanges=[e.value for e in self.config.default_exchanges],
        )
        self.store.set_state("scanning", message=f"Scan {trigger} running")
        self.store.push_scan(summary)

        opportunities: list[MarketOpportunity] = []
        errors: list[str] = []
        tf_completed = 0
        tf_failed = 0

        try:
            # Stage 1–3: discovery → volume filter → select (before OHLCV/TF matrix)
            universe = await discover_universe(self.config)
            candidates = universe.candidates
            summary.pairs_discovered = universe.discovered_pairs
            summary.pairs_eligible = universe.eligible_pairs
            summary.pairs_selected = universe.selected_pairs
            summary.pairs_targeted = universe.selected_pairs
            summary.ranking_method = universe.ranking_method
            summary.excluded_pairs = [
                {
                    "exchange": e.exchange,
                    "market_type": e.market_type,
                    "symbol": e.symbol,
                    "reason": e.reason,
                }
                for e in universe.excluded[:50]
            ]
            summary.per_market = [
                {
                    "exchange": b.exchange,
                    "market_type": b.market_type,
                    "discovered": b.discovered,
                    "eligible": b.eligible,
                    "selected": b.selected,
                    "excluded": b.excluded,
                }
                for b in universe.per_market
            ]
            errors.extend(universe.errors)

            execution_tfs = list(self.config.execution_timeframes)
            expected_tf_count = len(execution_tfs)
            summary.timeframe_analyses_attempted = len(candidates) * expected_tf_count

            self.store.set_state(
                "scanning",
                pairs_monitored=len(candidates),
                message=(
                    f"Scanning {len(candidates)} pairs × {expected_tf_count} TFs "
                    f"(discovered={universe.discovered_pairs})"
                ),
            )

            # Per-exchange concurrency; Spot/Futures share exchange semaphore (rate limit).
            semaphores: dict[ExchangeId, asyncio.Semaphore] = defaultdict(
                lambda: asyncio.Semaphore(self.config.max_concurrent_per_exchange)
            )

            # Track completions per pair key for accurate "fully scanned" accounting.
            pair_tf_ok: dict[tuple[str, str, str], int] = defaultdict(int)
            pair_tf_fail: dict[tuple[str, str, str], int] = defaultdict(int)

            async def _one(cand, execution_tf):
                nonlocal tf_completed, tf_failed
                key = (cand.exchange.value, cand.market_type.value, cand.symbol.upper())
                async with semaphores[cand.exchange]:
                    try:
                        opp = await analyze_candidate(
                            cand,
                            config=self.config,
                            cache=self.cache,
                            execution_timeframe=execution_tf,
                        )
                        # Engine WAIT/NO TRADE are valid completed analyses — not provider failures.
                        tf_completed += 1
                        pair_tf_ok[key] += 1
                        return opp
                    except Exception as exc:  # noqa: BLE001
                        tf_failed += 1
                        pair_tf_fail[key] += 1
                        errors.append(
                            f"{cand.exchange.value}:{cand.symbol}:{execution_tf.value}: {exc}"
                        )
                        logger.warning(
                            "Scan failed for %s %s %s %s: %s",
                            cand.exchange.value,
                            cand.market_type.value,
                            cand.symbol,
                            execution_tf.value,
                            exc,
                        )
                        return None

            jobs = [_one(c, tf) for c in candidates for tf in execution_tfs]
            results = await asyncio.gather(*jobs, return_exceptions=False)
            for item in results:
                if item is not None:
                    opportunities.append(item)

            # Pair-level completion (all execution TFs must complete).
            fully = partial = failed_pairs = 0
            all_keys = {
                (c.exchange.value, c.market_type.value, c.symbol.upper())
                for c in candidates
            }
            for key in all_keys:
                ok = pair_tf_ok.get(key, 0)
                fail = pair_tf_fail.get(key, 0)
                if ok == expected_tf_count and fail == 0:
                    fully += 1
                elif ok > 0:
                    partial += 1
                else:
                    failed_pairs += 1

            summary.pairs_scanned = fully
            summary.pairs_partial = partial
            summary.pairs_failed = failed_pairs
            summary.timeframe_analyses_completed = tf_completed
            summary.timeframe_analyses_failed = tf_failed

            self.store.replace_opportunities(opportunities)
            ready = sum(1 for o in opportunities if o.actionable)
            long_c = sum(
                1
                for o in opportunities
                if o.actionable and o.direction and o.direction.value == "LONG"
            )
            short_c = sum(
                1
                for o in opportunities
                if o.actionable and o.direction and o.direction.value == "SHORT"
            )
            summary.opportunities_found = len(opportunities)
            summary.ready_count = ready
            summary.long_count = long_c
            summary.short_count = short_c
            summary.errors = errors[:40]

            incomplete = (
                bool(universe.errors)
                or partial > 0
                or failed_pairs > 0
                or tf_failed > 0
            )
            if not candidates and universe.errors and not opportunities:
                summary.status = "failed"
            elif incomplete:
                summary.status = "completed_partial"
            else:
                summary.status = "completed"

            finished = datetime.now(timezone.utc)
            summary.finished_at = finished
            summary.duration_seconds = (finished - started).total_seconds()

            # Soft persist after summary is final — never fails the scan.
            try:
                from app.db.repositories.scanner import persist_scan_bundle

                persist_result = await persist_scan_bundle(
                    summary=summary,
                    opportunities=opportunities,
                    config=self.config,
                    trigger=trigger,
                )
                if not persist_result.get("persisted"):
                    logger.info(
                        "Scanner persistence skipped/soft-failed: %s",
                        persist_result.get("reason"),
                    )
            except Exception as persist_exc:  # noqa: BLE001
                logger.warning(
                    "Scanner persistence soft-error (in-memory retained): %s",
                    persist_exc,
                )
        except Exception as exc:  # noqa: BLE001
            summary.status = "failed"
            summary.errors = [str(exc)]
            logger.exception("Full scan failed: %s", exc)
        finally:
            if summary.finished_at is None:
                finished = datetime.now(timezone.utc)
                summary.finished_at = finished
                summary.duration_seconds = (finished - started).total_seconds()
            self.store.push_scan(summary)
            idle_state = "idle" if summary.status in (
                "completed",
                "completed_partial",
            ) else "error"
            self.store.set_state(
                idle_state,
                pairs_monitored=summary.pairs_selected,
                scan_interval_seconds=self.config.scan_interval_seconds,
                message=(
                    f"Scan {summary.status}: selected={summary.pairs_selected}, "
                    f"fully_scanned={summary.pairs_scanned}, "
                    f"tf_done={summary.timeframe_analyses_completed}/"
                    f"{summary.timeframe_analyses_attempted}, "
                    f"READY={summary.ready_count}, "
                    f"duration={summary.duration_seconds:.1f}s"
                ),
            )
        return summary


_scanner: MarketOpportunityScanner | None = None


def get_scanner() -> MarketOpportunityScanner:
    global _scanner
    if _scanner is None:
        _scanner = MarketOpportunityScanner()
    return _scanner
