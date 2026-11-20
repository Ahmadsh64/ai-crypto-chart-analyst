"""Tests for candle update / new-candle / duplicate prevention helpers used by frontend sync."""

from datetime import datetime, timezone

from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.market_data.normalizer import sort_and_dedupe_candles
from app.exchanges.types import Candle


def _c(ts: int, close: float, *, closed: bool = True) -> Candle:
    return Candle(
        timestamp=datetime.fromtimestamp(ts, tz=timezone.utc),
        open=close - 1,
        high=close + 1,
        low=close - 2,
        close=close,
        volume=1,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        is_closed=closed,
    )


def test_duplicate_timestamps_keep_latest() -> None:
    candles = sort_and_dedupe_candles(
        [
            _c(1_700_000_000, 100),
            _c(1_700_000_000, 101),
            _c(1_700_000_060, 102),
        ]
    )
    assert len(candles) == 2
    assert candles[0].close == 101


def test_new_candle_appends_when_timestamp_advances() -> None:
    historical = [_c(1_700_000_000, 100, closed=True)]
    live = _c(1_700_000_060, 105, closed=False)
    merged = sort_and_dedupe_candles([*historical, live])
    assert len(merged) == 2
    assert merged[-1].is_closed is False
    assert merged[-1].close == 105
