"""Bybit adapter tests with mocked HTTP client."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.exchanges.bybit import BybitExchange
from app.exchanges.exceptions import ExchangeRequestError, ExchangeUnsupportedError
from app.exchanges.types import MarketType, Timeframe


@pytest.mark.asyncio
async def test_fetch_ohlcv_linear_reverses_order() -> None:
    client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.text = ""
    response.json.return_value = {
        "retCode": 0,
        "result": {
            "list": [
                ["1700003600000", "2", "3", "1", "2.5", "20", "40"],
                ["1700000000000", "1", "1.5", "0.5", "1.2", "10", "15"],
            ]
        },
    }
    client.get = AsyncMock(return_value=response)

    exchange = BybitExchange(client)
    candles = await exchange.fetch_ohlcv(
        "BTC/USDT",
        Timeframe.H1,
        MarketType.LINEAR_PERPETUAL,
        limit=10,
    )
    assert len(candles) == 2
    assert candles[0].close == 1.2
    assert candles[1].close == 2.5
    assert candles[0].market_type == MarketType.LINEAR_PERPETUAL
    assert candles[0].exchange.value == "bybit"


@pytest.mark.asyncio
async def test_rejects_binance_futures_type() -> None:
    exchange = BybitExchange(AsyncMock())
    with pytest.raises(ExchangeUnsupportedError):
        await exchange.fetch_ohlcv(
            "BTC/USDT",
            Timeframe.H1,
            MarketType.USDT_M_FUTURES,
        )


@pytest.mark.asyncio
async def test_ticker_missing_symbol() -> None:
    client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.text = ""
    response.json.return_value = {"retCode": 0, "result": {"list": []}}
    client.get = AsyncMock(return_value=response)

    exchange = BybitExchange(client)
    with pytest.raises(ExchangeRequestError):
        await exchange.fetch_ticker("FAKE/USDT", MarketType.SPOT)
