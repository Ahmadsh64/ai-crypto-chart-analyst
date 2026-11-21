"""Phase 5.4.2 — market metadata search, pagination, cache, Bybit cursor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.exchanges.types import ExchangeId, MarketType, TradingPair
from app.main import create_app
from app.market_data.markets_cache import (
    MarketsMetadataCache,
    filter_trading_pairs,
    paginate_pairs,
)


def _pair(
    symbol: str,
    *,
    exchange: ExchangeId = ExchangeId.BINANCE,
    market_type: MarketType = MarketType.SPOT,
    active: bool = True,
) -> TradingPair:
    base, quote = symbol.split("/")
    return TradingPair(
        symbol=symbol,
        base=base,
        quote=quote,
        exchange=exchange,
        market_type=market_type,
        native_symbol=symbol.replace("/", ""),
        active=active,
    )


def test_filter_by_symbol_base_quote():
    pairs = [
        _pair("BTC/USDT"),
        _pair("ETH/USDT"),
        _pair("SOL/USDT"),
        _pair("BNB/USDT"),
    ]
    assert [p.symbol for p in filter_trading_pairs(pairs, "btc")] == ["BTC/USDT"]
    assert [p.symbol for p in filter_trading_pairs(pairs, "USDT")] == [
        "BTC/USDT",
        "ETH/USDT",
        "SOL/USDT",
        "BNB/USDT",
    ]
    assert [p.symbol for p in filter_trading_pairs(pairs, "ETHUSDT")] == ["ETH/USDT"]


def test_paginate_pairs():
    pairs = [_pair(f"C{i}/USDT") for i in range(5)]
    page, total = paginate_pairs(pairs, limit=2, offset=2)
    assert total == 5
    assert [p.symbol for p in page] == ["C2/USDT", "C3/USDT"]


def test_markets_cache_ttl_and_invalidate():
    cache = MarketsMetadataCache(ttl_seconds=60)
    pairs = [_pair("BTC/USDT")]
    cache.set(ExchangeId.BINANCE, MarketType.SPOT, pairs)
    assert cache.get(ExchangeId.BINANCE, MarketType.SPOT) is not None
    cache.invalidate(ExchangeId.BINANCE, MarketType.SPOT)
    assert cache.get(ExchangeId.BINANCE, MarketType.SPOT) is None


def test_list_markets_api_search_and_pagination():
    client = TestClient(create_app())
    pairs = [
        _pair("BTC/USDT"),
        _pair("ETH/USDT"),
        _pair("SOL/USDT"),
        _pair("DOGE/USDT"),
    ]
    manager = AsyncMock()
    manager.list_markets = AsyncMock(return_value=pairs)

    with (
        patch("app.api.routes.market.get_exchange_manager", return_value=manager),
        patch("app.market_data.markets_cache.get_markets_cache") as cache_factory,
    ):
        cache = MarketsMetadataCache(ttl_seconds=60)
        cache_factory.return_value = cache
        res = client.get(
            "/api/v1/markets",
            params={
                "exchange": "binance",
                "market_type": "spot",
                "search": "SOL",
                "limit": 10,
                "offset": 0,
                "refresh": True,
            },
        )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["count"] == 1
    assert data["pairs"][0]["symbol"] == "SOL/USDT"
    assert data["cache_hit"] is False


def test_list_markets_uses_cache_on_second_call():
    client = TestClient(create_app())
    pairs = [_pair("BTC/USDT"), _pair("ETH/USDT")]
    manager = AsyncMock()
    manager.list_markets = AsyncMock(return_value=pairs)
    cache = MarketsMetadataCache(ttl_seconds=60)

    with (
        patch("app.api.routes.market.get_exchange_manager", return_value=manager),
        patch("app.market_data.markets_cache.get_markets_cache", return_value=cache),
    ):
        r1 = client.get(
            "/api/v1/markets",
            params={"exchange": "binance", "market_type": "spot", "refresh": True},
        )
        r2 = client.get(
            "/api/v1/markets",
            params={"exchange": "binance", "market_type": "spot"},
        )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["cache_hit"] is False
    assert r2.json()["cache_hit"] is True
    assert manager.list_markets.await_count == 1


@pytest.mark.asyncio
async def test_bybit_list_markets_paginates_cursor():
    from app.exchanges.bybit import BybitExchange

    page1 = {
        "retCode": 0,
        "result": {
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "baseCoin": "BTC",
                    "quoteCoin": "USDT",
                    "status": "Trading",
                    "contractType": "LinearPerpetual",
                }
            ],
            "nextPageCursor": "cursor-2",
        },
    }
    page2 = {
        "retCode": 0,
        "result": {
            "list": [
                {
                    "symbol": "ETHUSDT",
                    "baseCoin": "ETH",
                    "quoteCoin": "USDT",
                    "status": "Trading",
                    "contractType": "LinearPerpetual",
                }
            ],
            "nextPageCursor": "",
        },
    }
    exchange = BybitExchange(client=MagicMock())
    exchange._get = AsyncMock(side_effect=[page1, page2])
    pairs = await exchange.list_markets(MarketType.LINEAR_PERPETUAL)
    assert [p.symbol for p in pairs] == ["BTC/USDT", "ETH/USDT"]
    assert exchange._get.await_count == 2
