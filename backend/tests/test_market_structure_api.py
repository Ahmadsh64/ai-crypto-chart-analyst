"""API tests for GET /api/v1/market-structure (mocked exchange)."""

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
        # gentle sine-like path to create swings
        close = 100 + (i % 17) - 8 + i * 0.05
        high = close + 2
        low = close - 2
        out.append(
            Candle(
                timestamp=base + timedelta(hours=i),
                open=close - 0.5,
                high=high,
                low=low,
                close=close,
                volume=100,
                exchange=ExchangeId.BINANCE,
                symbol="BTC/USDT",
                market_type=MarketType.SPOT,
                is_closed=True,
            )
        )
    return out


def test_market_structure_endpoint() -> None:
    manager = AsyncMock()
    manager.fetch_ohlcv = AsyncMock(return_value=_candles(80))

    with patch(
        "app.services.market_structure_service.get_exchange_manager",
        return_value=manager,
    ):
        response = client.get(
            "/api/v1/market-structure",
            params={
                "exchange": "binance",
                "market_type": "spot",
                "symbol": "BTC/USDT",
                "timeframe": "1h",
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["exchange"] == "binance"
    assert data["symbol"] == "BTC/USDT"
    assert "snapshot" in data
    assert "bias" in data["snapshot"]
    assert data["config"]["config_version"].startswith("ms-v")
    assert data["include_unconfirmed"] is False
    manager.fetch_ohlcv.assert_awaited_once()
