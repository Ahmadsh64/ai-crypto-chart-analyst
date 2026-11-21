"""Exchange registry / facade."""

from datetime import datetime

import httpx

from app.exchanges.base import BaseExchange
from app.exchanges.binance import BinanceExchange
from app.exchanges.bybit import BybitExchange
from app.exchanges.exceptions import ExchangeUnsupportedError
from app.exchanges.http import DEFAULT_TIMEOUT
from app.exchanges.types import (
    Candle,
    ExchangeId,
    ExchangeInfo,
    MarketType,
    Ticker,
    Timeframe,
    TradingPair,
)


class ExchangeManager:
    """Resolve the correct adapter for exchange + market type."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            headers={"User-Agent": "AI-Crypto-Chart-Analyst/0.1"},
            follow_redirects=True,
            timeout=DEFAULT_TIMEOUT,
        )
        self._exchanges: dict[ExchangeId, BaseExchange] = {
            ExchangeId.BINANCE: BinanceExchange(self._client),
            ExchangeId.BYBIT: BybitExchange(self._client),
        }

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def get(self, exchange_id: ExchangeId) -> BaseExchange:
        try:
            return self._exchanges[exchange_id]
        except KeyError as exc:
            raise ExchangeUnsupportedError(
                f"Unknown exchange: {exchange_id}",
                exchange=str(exchange_id),
            ) from exc

    def list_exchanges(self) -> list[ExchangeInfo]:
        return [
            ExchangeInfo(
                id=ExchangeId.BINANCE,
                name="Binance",
                market_types=[MarketType.SPOT, MarketType.USDT_M_FUTURES],
            ),
            ExchangeInfo(
                id=ExchangeId.BYBIT,
                name="Bybit",
                market_types=[MarketType.SPOT, MarketType.LINEAR_PERPETUAL],
            ),
        ]

    async def ping_all(self) -> dict[ExchangeId, bool]:
        results: dict[ExchangeId, bool] = {}
        for exchange_id, adapter in self._exchanges.items():
            results[exchange_id] = await adapter.ping()
        return results

    async def list_markets(
        self,
        exchange_id: ExchangeId,
        market_type: MarketType,
    ) -> list[TradingPair]:
        return await self.get(exchange_id).list_markets(market_type)

    async def fetch_ohlcv(
        self,
        exchange_id: ExchangeId,
        symbol: str,
        timeframe: Timeframe,
        market_type: MarketType,
        *,
        limit: int = 500,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Candle]:
        return await self.get(exchange_id).fetch_ohlcv(
            symbol,
            timeframe,
            market_type,
            limit=limit,
            start=start,
            end=end,
        )

    async def fetch_ticker(
        self,
        exchange_id: ExchangeId,
        symbol: str,
        market_type: MarketType,
    ) -> Ticker:
        return await self.get(exchange_id).fetch_ticker(symbol, market_type)

    async def fetch_tickers_24h(
        self,
        exchange_id: ExchangeId,
        market_type: MarketType,
    ) -> list[Ticker]:
        """Bulk 24h tickers when the adapter supports a category/all endpoint."""
        return await self.get(exchange_id).fetch_tickers_24h(market_type)


_manager: ExchangeManager | None = None


def get_exchange_manager() -> ExchangeManager:
    global _manager
    if _manager is None:
        _manager = ExchangeManager()
    return _manager


async def shutdown_exchange_manager() -> None:
    global _manager
    if _manager is not None:
        await _manager.aclose()
        _manager = None
