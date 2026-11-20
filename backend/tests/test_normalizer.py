"""Unit tests for OHLCV normalization (deterministic fixtures)."""

from datetime import datetime, timezone

import pytest

from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.market_data.normalizer import (
    assert_homogeneous_series,
    is_valid_ohlc,
    ms_to_utc,
    normalize_binance_kline,
    normalize_bybit_kline,
    sort_and_dedupe_candles,
    to_internal_symbol,
    to_native_symbol,
)


def test_symbol_roundtrip() -> None:
    assert to_native_symbol("BTC/USDT") == "BTCUSDT"
    assert to_internal_symbol("BTCUSDT") == "BTC/USDT"
    assert to_internal_symbol("ETHUSDT") == "ETH/USDT"


def test_timestamp_conversion_utc() -> None:
    dt = ms_to_utc(1_700_000_000_000)
    assert dt.tzinfo == timezone.utc
    assert dt == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)


def test_ohlc_validation() -> None:
    assert is_valid_ohlc(10, 12, 9, 11, 1)
    assert not is_valid_ohlc(10, 9, 8, 11, 1)  # high < open/close
    assert not is_valid_ohlc(10, 12, 11, 9, 1)  # low > close
    assert not is_valid_ohlc(10, 12, 9, 11, -1)


def test_normalize_binance_kline() -> None:
    row = [
        1_700_000_000_000,
        "42000.1",
        "42100.5",
        "41900.2",
        "42050.0",
        "12.5",
        1_700_000_059_999,
        "500000.0",
        42,
        "6.0",
        "250000.0",
        "0",
    ]
    candle = normalize_binance_kline(
        row,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        now=datetime(2023, 11, 15, tzinfo=timezone.utc),
    )
    assert candle is not None
    assert candle.open == 42000.1
    assert candle.high == 42100.5
    assert candle.low == 41900.2
    assert candle.close == 42050.0
    assert candle.volume == 12.5
    assert candle.trades == 42
    assert candle.exchange == ExchangeId.BINANCE
    assert candle.symbol == "BTC/USDT"
    assert candle.market_type == MarketType.SPOT
    assert candle.is_closed is True
    assert candle.timestamp == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)


def test_normalize_binance_rejects_invalid_ohlc() -> None:
    row = [
        1_700_000_000_000,
        "10",
        "9",  # high < open
        "8",
        "11",
        "1",
        1_700_000_059_999,
        "1",
        1,
        "0",
        "0",
        "0",
    ]
    assert (
        normalize_binance_kline(
            row,
            exchange=ExchangeId.BINANCE,
            symbol="BTC/USDT",
            market_type=MarketType.SPOT,
        )
        is None
    )


def test_normalize_bybit_kline_and_sort() -> None:
    newer = ["1700003600000", "1", "2", "0.5", "1.5", "10", "15"]
    older = ["1700000000000", "1", "1.2", "0.9", "1.1", "8", "9"]
    candles = [
        c
        for c in [
            normalize_bybit_kline(
                newer,
                exchange=ExchangeId.BYBIT,
                symbol="BTC/USDT",
                market_type=MarketType.LINEAR_PERPETUAL,
                timeframe=Timeframe.H1,
                now=datetime(2023, 11, 15, tzinfo=timezone.utc),
            ),
            normalize_bybit_kline(
                older,
                exchange=ExchangeId.BYBIT,
                symbol="BTC/USDT",
                market_type=MarketType.LINEAR_PERPETUAL,
                timeframe=Timeframe.H1,
                now=datetime(2023, 11, 15, tzinfo=timezone.utc),
            ),
            normalize_bybit_kline(
                older,
                exchange=ExchangeId.BYBIT,
                symbol="BTC/USDT",
                market_type=MarketType.LINEAR_PERPETUAL,
                timeframe=Timeframe.H1,
                now=datetime(2023, 11, 15, tzinfo=timezone.utc),
            ),
        ]
        if c is not None
    ]
    ordered = sort_and_dedupe_candles(candles)
    assert len(ordered) == 2
    assert ordered[0].timestamp < ordered[1].timestamp
    assert ordered[0].close == 1.1


def test_refuse_mixed_exchange_series() -> None:
    a = Candle(
        timestamp=datetime(2023, 1, 1, tzinfo=timezone.utc),
        open=1,
        high=2,
        low=0.5,
        close=1.5,
        volume=1,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
    )
    b = a.model_copy(update={"exchange": ExchangeId.BYBIT})
    with pytest.raises(ValueError, match="mix"):
        assert_homogeneous_series([a, b])


def test_candle_model_rejects_bad_ohlc() -> None:
    with pytest.raises(Exception):
        Candle(
            timestamp=datetime(2023, 1, 1, tzinfo=timezone.utc),
            open=10,
            high=9,
            low=8,
            close=11,
            volume=1,
            exchange=ExchangeId.BINANCE,
            symbol="BTC/USDT",
            market_type=MarketType.SPOT,
        )
