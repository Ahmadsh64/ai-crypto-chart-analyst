"""
Central exchange stream multiplexer.

One exchange WebSocket connection per (exchange, market_type).
Frontend subscriptions are ref-counted; unused topics are unsubscribed.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.market_data.exchange_streams import (
    BaseExchangeStream,
    BinanceStream,
    BybitStream,
    StreamTopic,
)
from app.market_data.ws_messages import MarketWsMessage, WsMessageType

logger = logging.getLogger(__name__)

BroadcastHandler = Callable[[MarketWsMessage], Awaitable[None]]

STALE_AFTER = timedelta(seconds=15)


@dataclass
class _ClientSub:
    client_id: str
    topic: StreamTopic


@dataclass
class StreamManager:
    """Ref-counted exchange stream manager shared across frontend clients."""

    _clients: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    _topic_refs: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _topics: dict[str, StreamTopic] = field(default_factory=dict)
    _streams: dict[tuple[ExchangeId, MarketType], BaseExchangeStream] = field(default_factory=dict)
    _broadcasters: set[BroadcastHandler] = field(default_factory=set)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _monitor_task: asyncio.Task | None = None

    def add_broadcaster(self, handler: BroadcastHandler) -> None:
        self._broadcasters.add(handler)

    def remove_broadcaster(self, handler: BroadcastHandler) -> None:
        self._broadcasters.discard(handler)

    async def start(self) -> None:
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._stale_monitor(), name="stream-stale-monitor")

    async def stop(self) -> None:
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        for stream in list(self._streams.values()):
            await stream.stop()
        self._streams.clear()

    async def subscribe(
        self,
        client_id: str,
        *,
        exchange: ExchangeId,
        market_type: MarketType,
        symbol: str,
        timeframe: Timeframe,
        ticker_only: bool = False,
    ) -> StreamTopic:
        topic = StreamTopic(
            exchange=exchange,
            market_type=market_type,
            symbol=symbol.upper(),
            timeframe=None if ticker_only else timeframe,
            include_ticker=True,
            include_kline=not ticker_only,
            include_trade=not ticker_only,
        )
        async with self._lock:
            key = topic.key
            if key not in self._clients[client_id]:
                self._clients[client_id].add(key)
                self._topic_refs[key] += 1
                self._topics[key] = topic
                await self._rebuild_stream(exchange, market_type)
        return topic

    async def unsubscribe(
        self,
        client_id: str,
        *,
        exchange: ExchangeId | None = None,
        market_type: MarketType | None = None,
        symbol: str | None = None,
        timeframe: Timeframe | None = None,
        all_topics: bool = False,
    ) -> None:
        async with self._lock:
            current = list(self._clients.get(client_id, set()))
            removed_pairs: set[tuple[ExchangeId, MarketType]] = set()
            for key in current:
                topic = self._topics.get(key)
                if topic is None:
                    self._clients[client_id].discard(key)
                    continue
                if not all_topics:
                    if exchange and topic.exchange != exchange:
                        continue
                    if market_type and topic.market_type != market_type:
                        continue
                    if symbol and topic.symbol.upper() != symbol.upper():
                        continue
                    if timeframe and topic.timeframe and topic.timeframe != timeframe:
                        continue
                self._clients[client_id].discard(key)
                self._topic_refs[key] -= 1
                removed_pairs.add((topic.exchange, topic.market_type))
                if self._topic_refs[key] <= 0:
                    self._topic_refs.pop(key, None)
                    self._topics.pop(key, None)
            for pair in removed_pairs:
                await self._rebuild_stream(*pair)
            if not self._clients[client_id]:
                self._clients.pop(client_id, None)

    async def unsubscribe_client(self, client_id: str) -> None:
        await self.unsubscribe(client_id, all_topics=True)

    def connection_snapshot(self) -> list[dict]:
        rows = []
        now = datetime.now(timezone.utc)
        for (exchange, market_type), stream in self._streams.items():
            last = stream.last_message_at
            stale = last is None or (now - last) > STALE_AFTER
            rows.append(
                {
                    "exchange": exchange.value,
                    "market_type": market_type.value,
                    "connected": stream.is_connected,
                    "stale": stale and stream.is_connected,
                    "last_message_at": last.isoformat() if last else None,
                }
            )
        return rows

    async def _rebuild_stream(self, exchange: ExchangeId, market_type: MarketType) -> None:
        topics = [
            topic
            for topic in self._topics.values()
            if topic.exchange == exchange and topic.market_type == market_type
        ]
        # Merge by symbol for ticker/trade flags, but keep DISTINCT kline timeframes
        # so Multi-Timeframe (4h+1h+15m+5m) can share one exchange connection.
        by_symbol: dict[str, list[StreamTopic]] = {}
        for topic in topics:
            by_symbol.setdefault(topic.symbol.upper(), []).append(topic)

        merged: list[StreamTopic] = []
        for symbol, group in by_symbol.items():
            include_ticker = any(t.include_ticker for t in group)
            include_trade = any(t.include_trade for t in group)
            timeframes = {t.timeframe for t in group if t.timeframe is not None}
            if timeframes:
                for i, tf in enumerate(sorted(timeframes, key=lambda x: x.value)):
                    merged.append(
                        StreamTopic(
                            exchange=exchange,
                            market_type=market_type,
                            symbol=symbol,
                            timeframe=tf,
                            # Ticker/trade once per symbol (stream name set dedupes anyway).
                            include_ticker=include_ticker and i == 0,
                            include_kline=True,
                            include_trade=include_trade and i == 0,
                        )
                    )
            else:
                merged.append(
                    StreamTopic(
                        exchange=exchange,
                        market_type=market_type,
                        symbol=symbol,
                        timeframe=None,
                        include_ticker=include_ticker,
                        include_kline=False,
                        include_trade=include_trade,
                    )
                )

        key = (exchange, market_type)
        if not merged:
            stream = self._streams.pop(key, None)
            if stream is not None:
                await stream.stop()
            return

        stream = self._streams.get(key)
        if stream is None:
            stream = self._create_stream(exchange, market_type)
            self._streams[key] = stream
        await stream.set_topics(merged)

    def _create_stream(self, exchange: ExchangeId, market_type: MarketType) -> BaseExchangeStream:
        if exchange == ExchangeId.BINANCE:
            return BinanceStream(market_type, self._on_exchange_message, self._on_exchange_status)
        if exchange == ExchangeId.BYBIT:
            return BybitStream(market_type, self._on_exchange_message, self._on_exchange_status)
        raise ValueError(f"Unsupported exchange stream: {exchange}")

    async def _on_exchange_message(self, message: MarketWsMessage) -> None:
        await self._broadcast(message)

    async def _on_exchange_status(self, message: MarketWsMessage) -> None:
        await self._broadcast(message)

    async def _broadcast(self, message: MarketWsMessage) -> None:
        if not self._broadcasters:
            return
        await asyncio.gather(
            *(handler(message) for handler in list(self._broadcasters)),
            return_exceptions=True,
        )

    async def _stale_monitor(self) -> None:
        while True:
            await asyncio.sleep(5)
            now = datetime.now(timezone.utc)
            for (exchange, market_type), stream in list(self._streams.items()):
                last = stream.last_message_at
                if stream.is_connected and last is not None and now - last > STALE_AFTER:
                    await self._broadcast(
                        MarketWsMessage(
                            type=WsMessageType.CONNECTION_STATUS,
                            exchange=exchange,
                            market_type=market_type,
                            status="stale",
                            detail=f"No message for {(now - last).total_seconds():.0f}s",
                            exchange_ts=last,
                        )
                    )


_stream_manager: StreamManager | None = None


def get_stream_manager() -> StreamManager:
    global _stream_manager
    if _stream_manager is None:
        _stream_manager = StreamManager()
    return _stream_manager


async def shutdown_stream_manager() -> None:
    global _stream_manager
    if _stream_manager is not None:
        await _stream_manager.stop()
        _stream_manager = None
