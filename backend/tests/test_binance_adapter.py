"""Binance adapter tests with mocked HTTP client."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.exchanges.binance import BinanceExchange
from app.exchanges.exceptions import ExchangeRequestError, ExchangeUnsupportedError
from app.exchanges.types import MarketType, Timeframe


def _kline(ts: int, close: str = "42050") -> list:
    return [
        ts,
        "42000",
        "42100",
        "41900",
        close,
        "10",
        ts + 3_599_999,
        "420000",
        5,
        "4",
        "168000",
        "0",
    ]


@pytest.mark.asyncio
async def test_fetch_ohlcv_spot() -> None:
    client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = [_kline(1_700_000_000_000)]
    response.text = ""
    client.get = AsyncMock(return_value=response)

    exchange = BinanceExchange(client)
    candles = await exchange.fetch_ohlcv(
        "BTC/USDT",
        Timeframe.H1,
        MarketType.SPOT,
        limit=10,
    )
    assert len(candles) == 1
    assert candles[0].close == 42050.0
    assert candles[0].exchange.value == "binance"
    assert candles[0].market_type == MarketType.SPOT
    assert candles[0].symbol == "BTC/USDT"
    assert candles[0].timestamp == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
    assert "api.binance.com" in str(client.get.await_args.args[0])


@pytest.mark.asyncio
async def test_rejects_bybit_market_type() -> None:
    exchange = BinanceExchange(AsyncMock())
    with pytest.raises(ExchangeUnsupportedError):
        await exchange.fetch_ohlcv(
            "BTC/USDT",
            Timeframe.H1,
            MarketType.LINEAR_PERPETUAL,
        )


@pytest.mark.asyncio
async def test_invalid_symbol_error() -> None:
    client = AsyncMock()
    response = MagicMock()
    response.status_code = 400
    response.text = "Invalid symbol"
    client.get = AsyncMock(return_value=response)

    exchange = BinanceExchange(client)
    with pytest.raises(ExchangeRequestError):
        await exchange.fetch_ticker("FAKE/USDT", MarketType.SPOT)


@pytest.mark.asyncio
async def test_spot_and_futures_use_different_bases() -> None:
    client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = [_kline(1_700_000_000_000)]
    response.text = ""
    client.get = AsyncMock(return_value=response)

    exchange = BinanceExchange(client)
    await exchange.fetch_ohlcv("BTC/USDT", Timeframe.H1, MarketType.SPOT, limit=1)
    spot_url = str(client.get.await_args.args[0])
    await exchange.fetch_ohlcv("BTC/USDT", Timeframe.H1, MarketType.USDT_M_FUTURES, limit=1)
    futures_url = str(client.get.await_args.args[0])
    assert "api.binance.com" in spot_url
    assert "fapi.binance.com" in futures_url
