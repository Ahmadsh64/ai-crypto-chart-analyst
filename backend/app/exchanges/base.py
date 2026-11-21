"""Abstract exchange adapter interface."""

from abc import ABC, abstractmethod
from datetime import datetime

import httpx

from app.exchanges.types import (
    Candle,
    ExchangeId,
    MarketType,
    Ticker,
    Timeframe,
    TradingPair,
)


class BaseExchange(ABC):
    """Public-market-data adapter. No trading / withdrawal permissions."""

    exchange_id: ExchangeId
    supported_market_types: tuple[MarketType, ...]

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    @abstractmethod
    async def ping(self) -> bool:
        """Return True if the exchange public API is reachable."""

    @abstractmethod
    async def list_markets(self, market_type: MarketType) -> list[TradingPair]:
        """List active pairs for a market type."""

    @abstractmethod
    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        market_type: MarketType,
        *,
        limit: int = 500,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Candle]:
        """Fetch normalized OHLCV candles ascending by open time."""

    @abstractmethod
    async def fetch_ticker(
        self,
        symbol: str,
        market_type: MarketType,
    ) -> Ticker:
        """Fetch last price / 24h stats for a symbol."""

    async def fetch_tickers_24h(self, market_type: MarketType) -> list[Ticker]:
        """
        Bulk 24h tickers for ranking (optional).

        Default: empty list — adapters should override with a single bulk endpoint
        when the exchange supports it. volume_24h should prefer quote/turnover.
        """
        self.ensure_market_type(market_type)
        return []

    def ensure_market_type(self, market_type: MarketType) -> None:
        if market_type not in self.supported_market_types:
            from app.exchanges.exceptions import ExchangeUnsupportedError

            raise ExchangeUnsupportedError(
                f"{self.exchange_id.value} does not support market type '{market_type.value}'",
                exchange=self.exchange_id.value,
            )
