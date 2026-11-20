"""Exchange-facing WebSocket clients with reconnect and heartbeat."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.market_data.normalizer import to_native_symbol
from app.market_data.ws_messages import (
    BINANCE_INTERVAL,
    BYBIT_INTERVAL,
    MarketWsMessage,
    WsMessageType,
    parse_binance_payload,
    parse_bybit_payload,
)

logger = logging.getLogger(__name__)

MessageHandler = Callable[[MarketWsMessage], Awaitable[None]]
StatusHandler = Callable[[MarketWsMessage], Awaitable[None]]


@dataclass(frozen=True)
class StreamTopic:
    exchange: ExchangeId
    market_type: MarketType
    symbol: str
    timeframe: Timeframe | None = None
    include_ticker: bool = True
    include_kline: bool = True
    include_trade: bool = True

    @property
    def key(self) -> str:
        tf = self.timeframe.value if self.timeframe else "-"
        return f"{self.exchange.value}:{self.market_type.value}:{self.symbol.upper()}:{tf}"


@dataclass
class _ConnectionState:
    topics: set[str] = field(default_factory=set)
    task: asyncio.Task | None = None
    ws: ClientConnection | None = None
    connected: bool = False
    last_message_at: datetime | None = None
    req_id: int = 1


class BaseExchangeStream:
    exchange: ExchangeId

    def __init__(
        self,
        market_type: MarketType,
        on_message: MessageHandler,
        on_status: StatusHandler | None = None,
    ) -> None:
        self.market_type = market_type
        self.on_message = on_message
        self.on_status = on_status
        self._state = _ConnectionState()
        self._desired: dict[str, StreamTopic] = {}
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()

    @property
    def last_message_at(self) -> datetime | None:
        return self._state.last_message_at

    @property
    def is_connected(self) -> bool:
        return self._state.connected

    async def set_topics(self, topics: list[StreamTopic]) -> None:
        async with self._lock:
            self._desired = {t.key: t for t in topics}
            if self._state.task is None or self._state.task.done():
                self._stop.clear()
                self._state.task = asyncio.create_task(self._run_forever(), name=f"{self.exchange}-{self.market_type}")
            elif self._state.ws is not None and self._state.connected:
                await self._sync_subscriptions()

    async def stop(self) -> None:
        self._stop.set()
        if self._state.ws is not None:
            await self._state.ws.close()
        if self._state.task is not None:
            self._state.task.cancel()
            try:
                await self._state.task
            except asyncio.CancelledError:
                pass
            self._state.task = None
        self._state.connected = False

    async def _emit_status(self, status: str, detail: str | None = None) -> None:
        if not self.on_status:
            return
        await self.on_status(
            MarketWsMessage(
                type=WsMessageType.CONNECTION_STATUS,
                exchange=self.exchange,
                market_type=self.market_type,
                status=status,
                detail=detail,
            )
        )

    async def _run_forever(self) -> None:
        delay = 1.0
        while not self._stop.is_set():
            if not self._desired:
                await asyncio.sleep(0.5)
                continue
            try:
                await self._emit_status("connecting")
                async with websockets.connect(
                    self._url(),
                    ping_interval=20,
                    ping_timeout=20,
                    max_queue=1024,
                ) as ws:
                    self._state.ws = ws
                    self._state.connected = True
                    self._state.topics.clear()
                    delay = 1.0
                    await self._emit_status("connected")
                    await self._sync_subscriptions()
                    await self._read_loop(ws)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._state.connected = False
                self._state.ws = None
                logger.warning("%s %s stream error: %s", self.exchange.value, self.market_type.value, exc)
                await self._emit_status("reconnecting", str(exc))
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30.0)
            finally:
                self._state.connected = False
                self._state.ws = None

    async def _read_loop(self, ws: ClientConnection) -> None:
        raise NotImplementedError

    async def _sync_subscriptions(self) -> None:
        raise NotImplementedError

    def _url(self) -> str:
        raise NotImplementedError


class BinanceStream(BaseExchangeStream):
    exchange = ExchangeId.BINANCE

    def _url(self) -> str:
        if self.market_type == MarketType.USDT_M_FUTURES:
            return "wss://fstream.binance.com/ws"
        return "wss://stream.binance.com:9443/ws"

    def _stream_names(self, topic: StreamTopic) -> list[str]:
        native = to_native_symbol(topic.symbol).lower()
        names: list[str] = []
        if topic.include_ticker:
            names.append(f"{native}@ticker")
        if topic.include_trade:
            names.append(f"{native}@trade")
        if topic.include_kline and topic.timeframe is not None:
            names.append(f"{native}@kline_{BINANCE_INTERVAL[topic.timeframe]}")
        return names

    async def _sync_subscriptions(self) -> None:
        if self._state.ws is None:
            return
        desired_streams: set[str] = set()
        for topic in self._desired.values():
            desired_streams.update(self._stream_names(topic))

        to_sub = sorted(desired_streams - self._state.topics)
        to_unsub = sorted(self._state.topics - desired_streams)

        if to_unsub:
            self._state.req_id += 1
            await self._state.ws.send(
                json.dumps({"method": "UNSUBSCRIBE", "params": to_unsub, "id": self._state.req_id})
            )
            self._state.topics -= set(to_unsub)
        if to_sub:
            self._state.req_id += 1
            await self._state.ws.send(
                json.dumps({"method": "SUBSCRIBE", "params": to_sub, "id": self._state.req_id})
            )
            self._state.topics |= set(to_sub)

    async def _read_loop(self, ws: ClientConnection) -> None:
        async for raw in ws:
            self._state.last_message_at = datetime.now(timezone.utc)
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("result") is None and "id" in payload:
                continue
            msg = parse_binance_payload(payload, market_type=self.market_type)
            if msg is not None:
                await self.on_message(msg)


class BybitStream(BaseExchangeStream):
    exchange = ExchangeId.BYBIT

    def _url(self) -> str:
        if self.market_type == MarketType.LINEAR_PERPETUAL:
            return "wss://stream.bybit.com/v5/public/linear"
        return "wss://stream.bybit.com/v5/public/spot"

    def _args(self, topic: StreamTopic) -> list[str]:
        native = to_native_symbol(topic.symbol)
        args: list[str] = []
        if topic.include_ticker:
            args.append(f"tickers.{native}")
        if topic.include_trade:
            args.append(f"publicTrade.{native}")
        if topic.include_kline and topic.timeframe is not None:
            args.append(f"kline.{BYBIT_INTERVAL[topic.timeframe]}.{native}")
        return args

    async def _sync_subscriptions(self) -> None:
        if self._state.ws is None:
            return
        desired: set[str] = set()
        for topic in self._desired.values():
            desired.update(self._args(topic))
        to_sub = sorted(desired - self._state.topics)
        to_unsub = sorted(self._state.topics - desired)
        if to_unsub:
            await self._state.ws.send(json.dumps({"op": "unsubscribe", "args": to_unsub}))
            self._state.topics -= set(to_unsub)
        if to_sub:
            await self._state.ws.send(json.dumps({"op": "subscribe", "args": to_sub}))
            self._state.topics |= set(to_sub)

    async def _read_loop(self, ws: ClientConnection) -> None:
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=15.0)
            except TimeoutError:
                await ws.send(json.dumps({"op": "ping"}))
                continue
            self._state.last_message_at = datetime.now(timezone.utc)
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if payload.get("op") == "pong" or payload.get("ret_msg") == "pong":
                continue
            if payload.get("success") is True and payload.get("op") == "subscribe":
                continue
            for msg in parse_bybit_payload(payload, market_type=self.market_type):
                await self.on_message(msg)
