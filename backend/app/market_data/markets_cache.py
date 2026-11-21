"""In-memory TTL cache for exchange market metadata (Phase 5.4.2)."""

from __future__ import annotations

import time
from threading import Lock
from app.exchanges.types import ExchangeId, MarketType, TradingPair

# Refresh interval for instrument catalogs (seconds).
DEFAULT_TTL_SECONDS = 300.0


class MarketsMetadataCache:
    """Process-local cache keyed by (exchange, market_type)."""

    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
        self._ttl = max(1.0, float(ttl_seconds))
        self._lock = Lock()
        self._store: dict[tuple[str, str], tuple[float, list[TradingPair]]] = {}

    def get(self, exchange: ExchangeId, market_type: MarketType) -> list[TradingPair] | None:
        key = (exchange.value, market_type.value)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, pairs = entry
            if time.monotonic() >= expires_at:
                del self._store[key]
                return None
            return list(pairs)

    def set(
        self,
        exchange: ExchangeId,
        market_type: MarketType,
        pairs: list[TradingPair],
    ) -> None:
        key = (exchange.value, market_type.value)
        with self._lock:
            self._store[key] = (time.monotonic() + self._ttl, list(pairs))

    def invalidate(
        self,
        exchange: ExchangeId | None = None,
        market_type: MarketType | None = None,
    ) -> None:
        with self._lock:
            if exchange is None:
                self._store.clear()
                return
            if market_type is None:
                drop = [k for k in self._store if k[0] == exchange.value]
            else:
                drop = [(exchange.value, market_type.value)]
            for key in drop:
                self._store.pop(key, None)

_markets_cache = MarketsMetadataCache()


def get_markets_cache() -> MarketsMetadataCache:
    return _markets_cache


def filter_trading_pairs(
    pairs: list[TradingPair],
    search: str | None,
) -> list[TradingPair]:
    """Filter by symbol, native symbol, base, or quote (case-insensitive)."""
    if not search:
        return list(pairs)
    needle = search.strip().upper().replace("-", "/").replace(" ", "")
    if not needle:
        return list(pairs)
    needle_compact = needle.replace("/", "")
    out: list[TradingPair] = []
    for p in pairs:
        symbol_u = p.symbol.upper()
        native_u = p.native_symbol.upper()
        base_u = (p.base or "").upper()
        quote_u = (p.quote or "").upper()
        if (
            needle in symbol_u
            or needle_compact in native_u
            or needle_compact in symbol_u.replace("/", "")
            or needle in native_u
            or needle == base_u
            or needle == quote_u
            or needle_compact == base_u
            or base_u.startswith(needle_compact)
        ):
            out.append(p)
    return out


def paginate_pairs(
    pairs: list[TradingPair],
    *,
    limit: int | None,
    offset: int,
) -> tuple[list[TradingPair], int]:
    total = len(pairs)
    start = max(0, int(offset))
    if limit is None:
        return pairs[start:], total
    lim = max(1, min(int(limit), 5000))
    return pairs[start : start + lim], total
