"""Symbol and candle normalization helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from app.core.logging import get_logger
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.market_data.candles import timeframe_to_seconds

logger = get_logger(__name__)


def to_native_symbol(symbol: str) -> str:
    """Convert BTC/USDT -> BTCUSDT."""
    return symbol.replace("/", "").replace("-", "").upper()


def to_internal_symbol(
    native: str,
    quote_candidates: tuple[str, ...] = ("USDT", "USDC", "USD", "BTC", "ETH"),
) -> str:
    """Best-effort BTCUSDT -> BTC/USDT."""
    native = native.upper()
    if "/" in native:
        return native
    for quote in quote_candidates:
        if native.endswith(quote) and len(native) > len(quote):
            base = native[: -len(quote)]
            return f"{base}/{quote}"
    return native


def ms_to_utc(ms: int | float | str) -> datetime:
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)


def is_valid_ohlc(open_: float, high: float, low: float, close: float, volume: float) -> bool:
    vals = (open_, high, low, close, volume)
    if not all(v == v and abs(v) != float("inf") for v in vals):
        return False
    if volume < 0:
        return False
    if high < low:
        return False
    if high < max(open_, close):
        return False
    if low > min(open_, close):
        return False
    return True


def normalize_binance_kline(
    row: list,
    *,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    now: datetime | None = None,
) -> Candle | None:
    """Map a Binance kline array row to Candle. Returns None if OHLC is invalid."""
    open_, high, low, close = float(row[1]), float(row[2]), float(row[3]), float(row[4])
    volume = float(row[5])
    if not is_valid_ohlc(open_, high, low, close, volume):
        logger.debug("Dropping invalid Binance OHLC row at %s", row[0])
        return None

    close_time = ms_to_utc(row[6])
    current = now or datetime.now(timezone.utc)
    try:
        return Candle(
            timestamp=ms_to_utc(row[0]),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
            exchange=exchange,
            symbol=symbol,
            market_type=market_type,
            is_closed=close_time < current,
            close_time=close_time,
            quote_volume=float(row[7]) if len(row) > 7 else None,
            trades=int(row[8]) if len(row) > 8 else None,
        )
    except ValidationError:
        return None


def normalize_bybit_kline(
    row: list[str],
    *,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    timeframe: Timeframe,
    now: datetime | None = None,
) -> Candle | None:
    """
    Map a Bybit v5 kline row to Candle.

    Bybit list item: [start, open, high, low, close, volume, turnover]
    Close time is inferred from timeframe; the newest candle may still be forming.
    """
    open_, high, low, close = float(row[1]), float(row[2]), float(row[3]), float(row[4])
    volume = float(row[5])
    if not is_valid_ohlc(open_, high, low, close, volume):
        logger.debug("Dropping invalid Bybit OHLC row at %s", row[0])
        return None

    start = ms_to_utc(row[0])
    close_time = start + timedelta(seconds=timeframe_to_seconds(timeframe)) - timedelta(milliseconds=1)
    current = now or datetime.now(timezone.utc)
    try:
        return Candle(
            timestamp=start,
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
            exchange=exchange,
            symbol=symbol,
            market_type=market_type,
            is_closed=close_time < current,
            close_time=close_time,
            quote_volume=float(row[6]) if len(row) > 6 else None,
        )
    except ValidationError:
        return None


def sort_and_dedupe_candles(candles: list[Candle]) -> list[Candle]:
    """Sort ascending and drop duplicate open timestamps (keep last)."""
    by_ts: dict[datetime, Candle] = {}
    for candle in candles:
        by_ts[candle.timestamp] = candle
    return [by_ts[key] for key in sorted(by_ts)]


def assert_homogeneous_series(candles: list[Candle]) -> None:
    """Ensure a series never mixes exchanges or market types."""
    if not candles:
        return
    exchange = candles[0].exchange
    market_type = candles[0].market_type
    symbol = candles[0].symbol
    for candle in candles[1:]:
        if candle.exchange != exchange or candle.market_type != market_type:
            raise ValueError("Cannot mix exchanges or market types in one candle series")
        if candle.symbol != symbol:
            raise ValueError("Cannot mix symbols in one candle series")
