"""Append-only execution ledger (Phase 5.2.3)."""

from __future__ import annotations

from app.replay.costs.models import LedgerEntry


class ExecutionLedger:
    """Append-only ledger with duplicate source-event rejection."""

    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []
        self._by_source: set[str] = set()
        self._by_id: dict[str, LedgerEntry] = {}

    def reset(self) -> None:
        self._entries.clear()
        self._by_source.clear()
        self._by_id.clear()

    def __len__(self) -> int:
        return len(self._entries)

    def has_source(self, source_event_id: str) -> bool:
        return source_event_id in self._by_source

    def append(self, entry: LedgerEntry) -> bool:
        """Append if source_event_id unseen. Returns True if added."""
        if entry.source_event_id in self._by_source:
            return False
        self._by_source.add(entry.source_event_id)
        self._by_id[entry.execution_id] = entry
        self._entries.append(entry)
        return True

    def entries(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        trade_id: str | None = None,
    ) -> tuple[list[LedgerEntry], int]:
        items = list(self._entries)
        if trade_id:
            items = [e for e in items if e.trade_id == trade_id]
        total = len(items)
        return items[offset : offset + limit], total

    def all_entries(self) -> list[LedgerEntry]:
        return list(self._entries)

    def for_trade(self, trade_id: str) -> list[LedgerEntry]:
        return [e for e in self._entries if e.trade_id == trade_id]
