"""API tests for GET /api/v1/indicators (mocked exchange; no live network)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.exchanges.types import Candle, ExchangeId, MarketType
from app.main import app

client = TestClient(app)


def _candles(n: int = 80) -> list[Candle]:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    out: list[Candle] = []
    for i in range(n):
        close = 100.0 + i * 0.5
        out.append(
            Candle(
                timestamp=base + timedelta(minutes=15 * i),
                open=close - 0.2,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1000 + i,
                exchange=ExchangeId.BINANCE,
                symbol="BTC/USDT",
                market_type=MarketType.SPOT,
                is_closed=True,
            )
        )
    return out


def test_indicators_catalog() -> None:
    response = client.get("/api/v1/indicators/catalog")
    assert response.status_code == 200
    data = response.json()
    ids = {item["id"] for item in data["indicators"]}
    assert "ema_20" in ids
    assert "rsi_14" in ids
    assert "macd" in ids


def test_get_indicators_latest() -> None:
    manager = AsyncMock()
    manager.fetch_ohlcv = AsyncMock(return_value=_candles(80))

    with patch("app.services.indicator_service.get_exchange_manager", return_value=manager):
        response = client.get(
            "/api/v1/indicators",
            params={
                "exchange": "binance",
                "market_type": "spot",
                "symbol": "BTC/USDT",
                "timeframe": "15m",
                "indicators": "ema_20,rsi_14,macd",
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["exchange"] == "binance"
    assert data["symbol"] == "BTC/USDT"
    assert data["include_forming"] is False
    assert data["indicators"]["ema_20"]["status"] == "ready"
    assert data["indicators"]["ema_20"]["value"] is not None
    assert data["indicators"]["rsi_14"]["status"] == "ready"
    assert data["indicators"]["macd"]["fields"]["macd"] is not None
    assert data["series"] == {}
    manager.fetch_ohlcv.assert_awaited_once()


def test_get_indicators_unknown_id() -> None:
    response = client.get(
        "/api/v1/indicators",
        params={
            "exchange": "binance",
            "market_type": "spot",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "indicators": "not_real",
        },
    )
    assert response.status_code == 400
