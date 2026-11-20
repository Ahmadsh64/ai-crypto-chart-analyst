"""Shared exchange / market enums and normalized data models."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ExchangeId(str, Enum):
    BINANCE = "binance"
    BYBIT = "bybit"


class MarketType(str, Enum):
    """Market venues — never treat these as interchangeable."""

    SPOT = "spot"
    USDT_M_FUTURES = "usdt_m_futures"  # Binance USDT-M
    LINEAR_PERPETUAL = "linear_perpetual"  # Bybit linear perp


class Timeframe(str, Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"


SUPPORTED_TIMEFRAMES: tuple[Timeframe, ...] = tuple(Timeframe)

DEFAULT_SYMBOLS: tuple[str, ...] = (
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "BNB/USDT",
    "XRP/USDT",
    "DOGE/USDT",
)


class Candle(BaseModel):
    """Normalized OHLCV candle (UTC). Never mix exchange or market_type series."""

    timestamp: datetime = Field(description="Candle open time (UTC)")
    open: float
    high: float
    low: float
    close: float
    volume: float
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    is_closed: bool = True
    close_time: datetime | None = None
    quote_volume: float | None = None
    trades: int | None = None

    @model_validator(mode="after")
    def validate_ohlc(self) -> "Candle":
        if self.high < self.low:
            raise ValueError("high must be >= low")
        if self.high < max(self.open, self.close):
            raise ValueError("high must be >= open and close")
        if self.low > min(self.open, self.close):
            raise ValueError("low must be <= open and close")
        if self.volume < 0:
            raise ValueError("volume must be >= 0")
        return self


class Ticker(BaseModel):
    """Normalized last-price ticker."""

    symbol: str
    exchange: ExchangeId
    market_type: MarketType
    last: float
    bid: float | None = None
    ask: float | None = None
    high_24h: float | None = None
    low_24h: float | None = None
    volume_24h: float | None = None
    change_pct_24h: float | None = None
    updated_at: datetime


class TradingPair(BaseModel):
    """Normalized tradable pair metadata."""

    symbol: str
    base: str
    quote: str
    exchange: ExchangeId
    market_type: MarketType
    native_symbol: str
    active: bool = True


class ExchangeInfo(BaseModel):
    id: ExchangeId
    name: str
    market_types: list[MarketType]
    status: Literal["ok", "degraded", "unavailable"] = "ok"
