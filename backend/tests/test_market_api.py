"""API tests for market routes using mocked exchange manager."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.exchanges.types import (
    Candle,
    ExchangeId,
    ExchangeInfo,
    MarketType,
    Ticker,
    Timeframe,
)
from app.main import app

client = TestClient(app)


def test_get_candles_binance_spot() -> None:
    candle = Candle(
        timestamp=datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc),
        open=42000,
        high=42100,
        low=41900,
        close=42050,
        volume=10,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        is_closed=True,
    )
    manager = AsyncMock()
    manager.fetch_ohlcv = AsyncMock(return_value=[candle])

    with patch("app.api.routes.market.get_exchange_manager", return_value=manager):
        response = client.get(
            "/api/v1/market/candles",
            params={
                "exchange": "binance",
                "market_type": "spot",
                "symbol": "BTC/USDT",
                "timeframe": "1h",
                "limit": 10,
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["exchange"] == "binance"
    assert data["market_type"] == "spot"
    assert data["count"] == 1
    assert data["latest_price"] == 42050.0
    assert data["data_source"] == "binance:spot"
    assert data["candles"][0]["close"] == 42050.0
    assert data["candles"][0]["is_closed"] is True
    manager.fetch_ohlcv.assert_awaited_once()


def test_get_ticker_bybit_linear() -> None:
    ticker = Ticker(
        symbol="BTC/USDT",
        exchange=ExchangeId.BYBIT,
        market_type=MarketType.LINEAR_PERPETUAL,
        last=65000.5,
        change_pct_24h=1.25,
        updated_at=datetime.now(timezone.utc),
    )
    manager = AsyncMock()
    manager.fetch_ticker = AsyncMock(return_value=ticker)

    with patch("app.api.routes.market.get_exchange_manager", return_value=manager):
        response = client.get(
            "/api/v1/market/ticker",
            params={
                "exchange": "bybit",
                "market_type": "linear_perpetual",
                "symbol": "BTCUSDT",
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ticker"]["last"] == 65000.5
    assert body["ticker"]["change_pct_24h"] == 1.25
    assert body["ticker"]["market_type"] == "linear_perpetual"
    assert body["data_source"] == "bybit:linear_perpetual"


def test_list_exchanges() -> None:
    manager = AsyncMock()
    manager.list_exchanges = lambda: [
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
    manager.ping_all = AsyncMock(
        return_value={ExchangeId.BINANCE: True, ExchangeId.BYBIT: True}
    )

    with patch("app.api.routes.market.get_exchange_manager", return_value=manager):
        response = client.get("/api/v1/exchanges")

    assert response.status_code == 200
    data = response.json()
    ids = {ex["id"] for ex in data["exchanges"]}
    assert ids == {"binance", "bybit"}
    assert "BTC/USDT" in data["default_symbols"]
    assert all(ex["status"] == "ok" for ex in data["exchanges"])


def test_unsupported_market_type_returns_400() -> None:
    from app.exchanges.exceptions import ExchangeUnsupportedError

    manager = AsyncMock()
    manager.fetch_ohlcv = AsyncMock(
        side_effect=ExchangeUnsupportedError(
            "binance does not support market type 'linear_perpetual'",
            exchange="binance",
        )
    )

    with patch("app.api.routes.market.get_exchange_manager", return_value=manager):
        response = client.get(
            "/api/v1/market/candles",
            params={
                "exchange": "binance",
                "market_type": "linear_perpetual",
                "symbol": "BTC/USDT",
                "timeframe": "1h",
            },
        )

    assert response.status_code == 400


def test_exchange_error_schema() -> None:
    from app.exchanges.exceptions import ExchangeRequestError

    manager = AsyncMock()
    manager.fetch_ticker = AsyncMock(
        side_effect=ExchangeRequestError("boom", exchange="binance", status_code=500)
    )
    with patch("app.api.routes.market.get_exchange_manager", return_value=manager):
        response = client.get(
            "/api/v1/market/ticker",
            params={"exchange": "binance", "market_type": "spot", "symbol": "BTC/USDT"},
        )
    assert response.status_code == 502
    assert "detail" in response.json()
