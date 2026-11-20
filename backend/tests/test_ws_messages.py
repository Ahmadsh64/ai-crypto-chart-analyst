"""Unit tests for WebSocket payload normalization."""

from datetime import datetime, timezone

from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.market_data.stream_manager import StreamManager
from app.market_data.ws_messages import (
    WsMessageType,
    parse_binance_payload,
    parse_bybit_payload,
)


def test_parse_binance_ticker() -> None:
    payload = {
        "e": "24hrTicker",
        "E": 1_700_000_000_000,
        "s": "BTCUSDT",
        "c": "42000.5",
        "P": "1.25",
        "h": "43000",
        "l": "41000",
        "v": "1000",
        "b": "41999",
        "a": "42001",
    }
    msg = parse_binance_payload(payload, market_type=MarketType.SPOT)
    assert msg is not None
    assert msg.type == WsMessageType.TICKER_UPDATE
    assert msg.exchange == ExchangeId.BINANCE
    assert msg.symbol == "BTC/USDT"
    assert msg.data.last == 42000.5  # type: ignore[union-attr]
    assert msg.data.change_pct_24h == 1.25  # type: ignore[union-attr]
    assert msg.exchange_ts == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)


def test_parse_binance_kline_open_and_closed() -> None:
    payload = {
        "e": "kline",
        "E": 1_700_000_000_500,
        "s": "ETHUSDT",
        "k": {
            "t": 1_700_000_000_000,
            "T": 1_700_000_059_999,
            "s": "ETHUSDT",
            "i": "15m",
            "o": "2000",
            "h": "2010",
            "l": "1990",
            "c": "2005",
            "v": "12.5",
            "x": False,
        },
    }
    msg = parse_binance_payload(payload, market_type=MarketType.USDT_M_FUTURES)
    assert msg is not None
    assert msg.type == WsMessageType.CANDLE_UPDATE
    assert msg.timeframe == Timeframe.M15
    assert msg.data.is_closed is False  # type: ignore[union-attr]
    assert msg.data.close == 2005  # type: ignore[union-attr]

    payload["k"]["x"] = True
    closed = parse_binance_payload(payload, market_type=MarketType.USDT_M_FUTURES)
    assert closed is not None
    assert closed.data.is_closed is True  # type: ignore[union-attr]


def test_parse_binance_trade_and_combined_wrapper() -> None:
    wrapped = {
        "stream": "btcusdt@trade",
        "data": {
            "e": "trade",
            "E": 1_700_000_000_000,
            "s": "BTCUSDT",
            "t": 123,
            "p": "42000",
            "q": "0.01",
            "m": True,
        },
    }
    msg = parse_binance_payload(wrapped, market_type=MarketType.SPOT)
    assert msg is not None
    assert msg.type == WsMessageType.TRADE_UPDATE
    assert msg.data.side == "sell"  # type: ignore[union-attr]


def test_parse_bybit_ticker_kline_trade() -> None:
    ticker_msgs = parse_bybit_payload(
        {
            "topic": "tickers.BTCUSDT",
            "ts": 1_700_000_000_000,
            "data": {
                "symbol": "BTCUSDT",
                "lastPrice": "65000",
                "price24hPcnt": "0.02",
                "volume24h": "100",
            },
        },
        market_type=MarketType.LINEAR_PERPETUAL,
    )
    assert len(ticker_msgs) == 1
    assert ticker_msgs[0].data.change_pct_24h == 2.0  # type: ignore[union-attr]

    kline_msgs = parse_bybit_payload(
        {
            "topic": "kline.15.ETHUSDT",
            "ts": 1_700_000_000_000,
            "data": [
                {
                    "start": 1_700_000_000_000,
                    "end": 1_700_000_899_999,
                    "interval": "15",
                    "open": "2000",
                    "close": "2010",
                    "high": "2020",
                    "low": "1990",
                    "volume": "5",
                    "confirm": False,
                    "timestamp": 1_700_000_100_000,
                }
            ],
        },
        market_type=MarketType.SPOT,
    )
    assert len(kline_msgs) == 1
    assert kline_msgs[0].timeframe == Timeframe.M15
    assert kline_msgs[0].data.is_closed is False  # type: ignore[union-attr]

    trade_msgs = parse_bybit_payload(
        {
            "topic": "publicTrade.BTCUSDT",
            "ts": 1_700_000_000_000,
            "data": [{"T": 1_700_000_000_000, "s": "BTCUSDT", "S": "Buy", "v": "0.1", "p": "1", "i": "abc"}],
        },
        market_type=MarketType.SPOT,
    )
    assert trade_msgs[0].data.side == "buy"  # type: ignore[union-attr]


def test_stream_manager_refcounts_without_live_sockets() -> None:
    import asyncio

    manager = StreamManager()

    async def _run() -> None:
        await manager.subscribe(
            "c1",
            exchange=ExchangeId.BINANCE,
            market_type=MarketType.SPOT,
            symbol="BTC/USDT",
            timeframe=Timeframe.M15,
        )
        await manager.subscribe(
            "c2",
            exchange=ExchangeId.BINANCE,
            market_type=MarketType.SPOT,
            symbol="BTC/USDT",
            timeframe=Timeframe.M15,
        )
        assert manager._topic_refs[next(iter(manager._topics))] == 2
        await manager.unsubscribe_client("c1")
        assert manager._topic_refs[next(iter(manager._topics))] == 1
        await manager.unsubscribe_client("c2")
        assert manager._topics == {}
        await manager.stop()

    asyncio.run(_run())
