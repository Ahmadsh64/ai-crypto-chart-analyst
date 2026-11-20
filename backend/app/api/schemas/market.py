"""Market data request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.exchanges.types import (
    Candle,
    DEFAULT_SYMBOLS,
    ExchangeId,
    ExchangeInfo,
    MarketType,
    Ticker,
    Timeframe,
    TradingPair,
)


class ExchangesResponse(BaseModel):
    exchanges: list[ExchangeInfo]
    default_symbols: list[str] = Field(default_factory=lambda: list(DEFAULT_SYMBOLS))
    timeframes: list[Timeframe] = Field(default_factory=lambda: list(Timeframe))


class MarketsResponse(BaseModel):
    exchange: ExchangeId
    market_type: MarketType
    count: int
    pairs: list[TradingPair]
    last_updated: datetime
    data_source: str


class CandlesResponse(BaseModel):
    exchange: ExchangeId
    market_type: MarketType
    symbol: str
    timeframe: Timeframe
    count: int
    candles: list[Candle]
    latest_price: float | None = None
    last_updated: datetime
    data_source: str
    # Backward-compatible alias used by Phase 1 UI
    updated_at: datetime | None = None


class TickerResponse(BaseModel):
    ticker: Ticker
    last_updated: datetime
    data_source: str
