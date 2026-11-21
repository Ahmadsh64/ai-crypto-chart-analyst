"""Process-local OHLCV TTL cache for scanner (Phase 5.5)."""

from __future__ import annotations

import time
from threading import Lock

from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe


class OhlcvTtlCache:
    def __init__(self, ttl_seconds: float = 90.0) -> None:
        self._ttl = max(1.0, float(ttl_seconds))
        self._lock = Lock()
        self._store: dict[tuple[str, str, str, str], tuple[float, list[Candle]]] = {}

    def _key(
        self,
        exchange: ExchangeId,
        market_type: MarketType,
        symbol: str,
        timeframe: Timeframe,
    ) -> tuple[str, str, str, str]:
        return (exchange.value, market_type.value, symbol.upper(), timeframe.value)

    def get(
        self,
        exchange: ExchangeId,
        market_type: MarketType,
        symbol: str,
        timeframe: Timeframe,
    ) -> list[Candle] | None:
        key = self._key(exchange, market_type, symbol, timeframe)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, candles = entry
            if time.monotonic() >= expires_at:
                del self._store[key]
                return None
            return list(candles)

    def set(
        self,
        exchange: ExchangeId,
        market_type: MarketType,
        symbol: str,
        timeframe: Timeframe,
        candles: list[Candle],
    ) -> None:
        key = self._key(exchange, market_type, symbol, timeframe)
        with self._lock:
            self._store[key] = (time.monotonic() + self._ttl, list(candles))

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
