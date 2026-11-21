"""In-memory opportunity + scan history store (Phase 5.5)."""

from __future__ import annotations

from threading import Lock

from app.scanner.models import MarketOpportunity, ScanRunSummary, ScannerStatus
from app.scanner.ranking import sort_opportunities


class OpportunityStore:
    def __init__(self, history_limit: int = 20) -> None:
        self._lock = Lock()
        self._opportunities: dict[str, MarketOpportunity] = {}
        self._history: list[ScanRunSummary] = []
        self._history_limit = history_limit
        self._status = ScannerStatus()

    def replace_opportunities(self, items: list[MarketOpportunity]) -> None:
        ranked = sort_opportunities(items)
        with self._lock:
            self._opportunities = {o.opportunity_id: o for o in ranked}

    def list_opportunities(self) -> list[MarketOpportunity]:
        with self._lock:
            return list(self._opportunities.values())

    def get(self, opportunity_id: str) -> MarketOpportunity | None:
        with self._lock:
            return self._opportunities.get(opportunity_id)

    def push_scan(self, summary: ScanRunSummary) -> None:
        with self._lock:
            self._history.insert(0, summary)
            self._history = self._history[: self._history_limit]
            self._status.last_scan = summary
            if summary.status in ("completed", "completed_partial"):
                self._status.last_successful_scan_at = summary.finished_at
                self._status.pairs_scanned_total = summary.pairs_scanned
                self._status.message = (
                    "Last scan completed"
                    if summary.status == "completed"
                    else "Last scan completed with partial results"
                )
            elif summary.status == "failed":
                self._status.message = summary.errors[0] if summary.errors else "Scan failed"

    def history(self) -> list[ScanRunSummary]:
        with self._lock:
            return list(self._history)

    def set_state(
        self,
        state: str,
        *,
        next_scan_at=None,
        scan_interval_seconds: float | None = None,
        pairs_monitored: int | None = None,
        message: str | None = None,
    ) -> None:
        with self._lock:
            self._status.state = state  # type: ignore[assignment]
            if next_scan_at is not None:
                self._status.next_scan_at = next_scan_at
            if scan_interval_seconds is not None:
                self._status.scan_interval_seconds = scan_interval_seconds
            if pairs_monitored is not None:
                self._status.pairs_monitored = pairs_monitored
            if message is not None:
                self._status.message = message
            ready = long_c = short_c = 0
            waiting = approaching = invalidated = expired = data_unavail = 0
            for o in self._opportunities.values():
                st = o.status.value
                if st == "READY" and o.actionable:
                    ready += 1
                    if o.direction and o.direction.value == "LONG":
                        long_c += 1
                    elif o.direction and o.direction.value == "SHORT":
                        short_c += 1
                elif st == "WAITING":
                    waiting += 1
                elif st == "APPROACHING_ENTRY":
                    approaching += 1
                elif st == "INVALIDATED":
                    invalidated += 1
                elif st == "EXPIRED":
                    expired += 1
                elif st == "DATA_UNAVAILABLE":
                    data_unavail += 1
            self._status.qualified_opportunities = ready
            self._status.ready_opportunities = ready
            self._status.long_opportunities = long_c
            self._status.short_opportunities = short_c
            self._status.waiting_opportunities = waiting
            self._status.approaching_opportunities = approaching
            self._status.invalidated_opportunities = invalidated
            self._status.expired_opportunities = expired
            self._status.data_unavailable_opportunities = data_unavail

    def status(self) -> ScannerStatus:
        with self._lock:
            return self._status.model_copy(deep=True)


_store = OpportunityStore()


def get_opportunity_store() -> OpportunityStore:
    return _store
