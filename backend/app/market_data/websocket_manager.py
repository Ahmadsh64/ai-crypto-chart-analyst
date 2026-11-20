"""
Frontend WebSocket hub.

Tracks connected dashboard clients and forwards normalized exchange messages.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from app.analysis.indicators.models import IndicatorId
from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.market_data.indicator_runtime import get_indicator_runtime
from app.market_data.stream_manager import get_stream_manager
from app.market_data.liquidity_runtime import get_liquidity_runtime
from app.market_data.confluence_runtime import get_confluence_runtime
from app.market_data.multi_timeframe_runtime import get_multi_timeframe_runtime
from app.market_data.ob_fvg_runtime import get_ob_fvg_runtime
from app.market_data.structure_runtime import get_structure_runtime
from app.market_data.trade_plan_runtime import get_trade_plan_runtime
from app.market_data.decision_runtime import get_decision_runtime
from app.market_data.ws_messages import MarketWsMessage, WsMessageType
from app.services.indicator_service import parse_indicator_ids

logger = logging.getLogger(__name__)


@dataclass
class FrontendClient:
    client_id: str
    websocket: WebSocket
    subscriptions: set[str] = field(default_factory=set)
    queue: asyncio.Queue[MarketWsMessage] = field(default_factory=asyncio.Queue)


class WebsocketManager:
    """Manage frontend `/ws/market` clients and their subscriptions."""

    def __init__(self) -> None:
        self._clients: dict[str, FrontendClient] = {}
        self._lock = asyncio.Lock()
        self._attached = False

    async def attach(self) -> None:
        if self._attached:
            return
        manager = get_stream_manager()
        manager.add_broadcaster(self.broadcast)
        await manager.start()
        self._attached = True

    async def connect(self, websocket: WebSocket) -> FrontendClient:
        await self.attach()
        await websocket.accept()
        client = FrontendClient(client_id=str(uuid.uuid4()), websocket=websocket)
        async with self._lock:
            self._clients[client.client_id] = client
        await self._send(
            client,
            MarketWsMessage(
                type=WsMessageType.CONNECTION_STATUS,
                status="connected",
                detail=f"client {client.client_id}",
            ),
        )
        return client

    async def disconnect(self, client: FrontendClient) -> None:
        await get_stream_manager().unsubscribe_client(client.client_id)
        get_indicator_runtime().unsubscribe_client(client.client_id)
        get_structure_runtime().unsubscribe_client(client.client_id)
        get_liquidity_runtime().unsubscribe_client(client.client_id)
        get_ob_fvg_runtime().unsubscribe_client(client.client_id)
        await get_multi_timeframe_runtime().unsubscribe_streams(client.client_id)
        get_confluence_runtime().unsubscribe_client(client.client_id)
        get_trade_plan_runtime().unsubscribe_client(client.client_id)
        get_decision_runtime().unsubscribe_client(client.client_id)
        async with self._lock:
            self._clients.pop(client.client_id, None)

    async def broadcast(self, message: MarketWsMessage) -> None:
        await self._enqueue(message)
        # Recalculate indicators / structure / liquidity from candle updates (no new exchange WS).
        if message.type == WsMessageType.CANDLE_UPDATE:
            try:
                indicator_msg = await get_indicator_runtime().on_market_message(message)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Indicator runtime error: %s", exc)
                indicator_msg = None
            if indicator_msg is not None:
                await self._enqueue(indicator_msg)
            try:
                structure_msg = await get_structure_runtime().on_market_message(message)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Structure runtime error: %s", exc)
                structure_msg = None
            if structure_msg is not None:
                await self._enqueue(structure_msg)
            try:
                liquidity_msg = await get_liquidity_runtime().on_market_message(message)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Liquidity runtime error: %s", exc)
                liquidity_msg = None
            if liquidity_msg is not None:
                await self._enqueue(liquidity_msg)
            try:
                ob_fvg_msg = await get_ob_fvg_runtime().on_market_message(message)
            except Exception as exc:  # noqa: BLE001
                logger.warning("OB/FVG runtime error: %s", exc)
                ob_fvg_msg = None
            if ob_fvg_msg is not None:
                await self._enqueue(ob_fvg_msg)
            try:
                mtf_msg = await get_multi_timeframe_runtime().on_market_message(message)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Multi-timeframe runtime error: %s", exc)
                mtf_msg = None
            if mtf_msg is not None:
                await self._enqueue(mtf_msg)
            try:
                confluence_msg = await get_confluence_runtime().on_market_message(message)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Confluence runtime error: %s", exc)
                confluence_msg = None
            if confluence_msg is not None:
                await self._enqueue(confluence_msg)
            try:
                trade_plan_msg = await get_trade_plan_runtime().on_market_message(message)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Trade plan runtime error: %s", exc)
                trade_plan_msg = None
            if trade_plan_msg is not None:
                await self._enqueue(trade_plan_msg)
            try:
                decision_msg = await get_decision_runtime().on_market_message(message)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Decision runtime error: %s", exc)
                decision_msg = None
            if decision_msg is not None:
                await self._enqueue(decision_msg)

    async def _enqueue(self, message: MarketWsMessage) -> None:
        dead: list[str] = []
        for client_id, client in list(self._clients.items()):
            if not self._client_wants(client, message):
                continue
            try:
                await client.queue.put(message)
            except Exception:  # noqa: BLE001
                dead.append(client_id)
        for client_id in dead:
            self._clients.pop(client_id, None)

    @staticmethod
    def _client_wants(client: FrontendClient, message: MarketWsMessage) -> bool:
        """Only forward market updates matching a client's active subscriptions."""
        if message.type in {
            WsMessageType.CONNECTION_STATUS,
            WsMessageType.SUBSCRIPTION_ERROR,
            WsMessageType.SUBSCRIBED,
            WsMessageType.UNSUBSCRIBED,
            WsMessageType.INDICATOR_UPDATE,
            WsMessageType.STRUCTURE_UPDATE,
            WsMessageType.LIQUIDITY_UPDATE,
            WsMessageType.OB_FVG_UPDATE,
            WsMessageType.MULTI_TIMEFRAME_UPDATE,
            WsMessageType.CONFLUENCE_UPDATE,
            WsMessageType.TRADE_PLAN_UPDATE,
            WsMessageType.DECISION_UPDATE,
        }:
            if message.type in {
                WsMessageType.INDICATOR_UPDATE,
                WsMessageType.STRUCTURE_UPDATE,
                WsMessageType.LIQUIDITY_UPDATE,
                WsMessageType.OB_FVG_UPDATE,
                WsMessageType.MULTI_TIMEFRAME_UPDATE,
                WsMessageType.CONFLUENCE_UPDATE,
                WsMessageType.TRADE_PLAN_UPDATE,
                WsMessageType.DECISION_UPDATE,
            }:
                if not message.exchange or not message.symbol or not message.market_type:
                    return True
                symbol = message.symbol.upper()
                prefix = f"{message.exchange.value}:{message.market_type.value}:{symbol}:"
                return any(sub.startswith(prefix) for sub in client.subscriptions)
            # Connection status for a specific exchange/market is always useful.
            if message.type == WsMessageType.CONNECTION_STATUS and message.exchange and message.market_type:
                prefix = f"{message.exchange.value}:{message.market_type.value}:"
                return any(sub.startswith(prefix) for sub in client.subscriptions) or not client.subscriptions
            return True
        if not message.exchange or not message.symbol or not message.market_type:
            return True
        symbol = message.symbol.upper()
        prefix = f"{message.exchange.value}:{message.market_type.value}:{symbol}:"
        return any(sub.startswith(prefix) for sub in client.subscriptions)

    async def handle_client(self, websocket: WebSocket) -> None:
        client = await self.connect(websocket)
        sender = asyncio.create_task(self._sender_loop(client), name=f"ws-sender-{client.client_id}")
        try:
            while True:
                payload = await websocket.receive_json()
                await self._handle_action(client, payload)
        except WebSocketDisconnect:
            logger.info("Frontend WS disconnected: %s", client.client_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Frontend WS error %s: %s", client.client_id, exc)
            await self._send(
                client,
                MarketWsMessage(
                    type=WsMessageType.SUBSCRIPTION_ERROR,
                    status="error",
                    detail=str(exc),
                ),
            )
        finally:
            sender.cancel()
            await self.disconnect(client)

    async def _sender_loop(self, client: FrontendClient) -> None:
        try:
            while True:
                message = await client.queue.get()
                await self._send(client, message)
        except asyncio.CancelledError:
            return

    async def _send(self, client: FrontendClient, message: MarketWsMessage) -> None:
        await client.websocket.send_json(message.model_dump(mode="json"))

    async def _handle_action(self, client: FrontendClient, payload: dict[str, Any]) -> None:
        action = str(payload.get("action") or "").lower()
        try:
            if action == "subscribe":
                exchange = ExchangeId(payload["exchange"])
                market_type = MarketType(payload["market_type"])
                symbol = str(payload["symbol"])
                timeframe = Timeframe(payload.get("timeframe") or "1h")
                ticker_only = bool(payload.get("ticker_only", False))
                topic = await get_stream_manager().subscribe(
                    client.client_id,
                    exchange=exchange,
                    market_type=market_type,
                    symbol=symbol,
                    timeframe=timeframe,
                    ticker_only=ticker_only,
                )
                client.subscriptions.add(topic.key)
                await self._send(
                    client,
                    MarketWsMessage(
                        type=WsMessageType.SUBSCRIBED,
                        exchange=exchange,
                        market_type=market_type,
                        symbol=symbol.upper(),
                        timeframe=None if ticker_only else timeframe,
                        status="ok",
                        detail=topic.key,
                    ),
                )
                return

            if action == "unsubscribe":
                exchange = ExchangeId(payload["exchange"]) if payload.get("exchange") else None
                market_type = MarketType(payload["market_type"]) if payload.get("market_type") else None
                symbol = str(payload["symbol"]) if payload.get("symbol") else None
                timeframe = Timeframe(payload["timeframe"]) if payload.get("timeframe") else None
                all_topics = bool(payload.get("all", False))
                await get_stream_manager().unsubscribe(
                    client.client_id,
                    exchange=exchange,
                    market_type=market_type,
                    symbol=symbol,
                    timeframe=timeframe,
                    all_topics=all_topics,
                )
                if all_topics:
                    client.subscriptions.clear()
                else:
                    to_remove = []
                    for key in client.subscriptions:
                        parts = key.split(":")
                        if exchange and parts[0] != exchange.value:
                            continue
                        if market_type and parts[1] != market_type.value:
                            continue
                        if symbol and parts[2] != symbol.upper():
                            continue
                        if timeframe and parts[3] not in {timeframe.value, "-"}:
                            continue
                        to_remove.append(key)
                    for key in to_remove:
                        client.subscriptions.discard(key)
                await self._send(
                    client,
                    MarketWsMessage(
                        type=WsMessageType.UNSUBSCRIBED,
                        exchange=exchange,
                        market_type=market_type,
                        symbol=symbol,
                        timeframe=timeframe,
                        status="ok",
                    ),
                )
                return

            if action == "subscribe_indicators":
                exchange = ExchangeId(payload["exchange"])
                market_type = MarketType(payload["market_type"])
                symbol = str(payload["symbol"])
                timeframe = Timeframe(payload.get("timeframe") or "1h")
                raw_ids = payload.get("indicators")
                indicator_ids: list[IndicatorId] | None = None
                if raw_ids is not None:
                    if isinstance(raw_ids, str):
                        indicator_ids = parse_indicator_ids(raw_ids)
                    elif isinstance(raw_ids, list):
                        indicator_ids = parse_indicator_ids(",".join(str(x) for x in raw_ids))
                msg = await get_indicator_runtime().subscribe(
                    client.client_id,
                    exchange=exchange,
                    market_type=market_type,
                    symbol=symbol,
                    timeframe=timeframe,
                    indicator_ids=indicator_ids,
                )
                if msg is not None:
                    await self._send(client, msg)
                return

            if action == "unsubscribe_indicators":
                get_indicator_runtime().unsubscribe_client(client.client_id)
                await self._send(
                    client,
                    MarketWsMessage(
                        type=WsMessageType.UNSUBSCRIBED,
                        status="ok",
                        detail="indicators",
                    ),
                )
                return

            if action == "subscribe_structure":
                exchange = ExchangeId(payload["exchange"])
                market_type = MarketType(payload["market_type"])
                symbol = str(payload["symbol"])
                timeframe = Timeframe(payload.get("timeframe") or "1h")
                msg = await get_structure_runtime().subscribe(
                    client.client_id,
                    exchange=exchange,
                    market_type=market_type,
                    symbol=symbol,
                    timeframe=timeframe,
                )
                if msg is not None:
                    await self._send(client, msg)
                return

            if action == "unsubscribe_structure":
                get_structure_runtime().unsubscribe_client(client.client_id)
                await self._send(
                    client,
                    MarketWsMessage(
                        type=WsMessageType.UNSUBSCRIBED,
                        status="ok",
                        detail="structure",
                    ),
                )
                return

            if action == "subscribe_liquidity":
                exchange = ExchangeId(payload["exchange"])
                market_type = MarketType(payload["market_type"])
                symbol = str(payload["symbol"])
                timeframe = Timeframe(payload.get("timeframe") or "1h")
                msg = await get_liquidity_runtime().subscribe(
                    client.client_id,
                    exchange=exchange,
                    market_type=market_type,
                    symbol=symbol,
                    timeframe=timeframe,
                )
                if msg is not None:
                    await self._send(client, msg)
                return

            if action == "unsubscribe_liquidity":
                get_liquidity_runtime().unsubscribe_client(client.client_id)
                await self._send(
                    client,
                    MarketWsMessage(
                        type=WsMessageType.UNSUBSCRIBED,
                        status="ok",
                        detail="liquidity",
                    ),
                )
                return

            if action == "subscribe_ob_fvg":
                exchange = ExchangeId(payload["exchange"])
                market_type = MarketType(payload["market_type"])
                symbol = str(payload["symbol"])
                timeframe = Timeframe(payload.get("timeframe") or "1h")
                msg = await get_ob_fvg_runtime().subscribe(
                    client.client_id,
                    exchange=exchange,
                    market_type=market_type,
                    symbol=symbol,
                    timeframe=timeframe,
                )
                if msg is not None:
                    await self._send(client, msg)
                return

            if action == "unsubscribe_ob_fvg":
                get_ob_fvg_runtime().unsubscribe_client(client.client_id)
                await self._send(
                    client,
                    MarketWsMessage(
                        type=WsMessageType.UNSUBSCRIBED,
                        status="ok",
                        detail="ob_fvg",
                    ),
                )
                return

            if action == "subscribe_multi_timeframe":
                exchange = ExchangeId(payload["exchange"])
                market_type = MarketType(payload["market_type"])
                symbol = str(payload["symbol"])
                sub_key = f"{exchange.value}:{market_type.value}:{symbol.upper()}:mtf"
                client.subscriptions.add(sub_key)
                msg = await get_multi_timeframe_runtime().subscribe(
                    client.client_id,
                    exchange=exchange,
                    market_type=market_type,
                    symbol=symbol,
                )
                if msg is not None:
                    await self._send(client, msg)
                await self._send(
                    client,
                    MarketWsMessage(
                        type=WsMessageType.SUBSCRIBED,
                        exchange=exchange,
                        symbol=symbol,
                        market_type=market_type,
                        status="ok",
                        detail="multi_timeframe",
                    ),
                )
                return

            if action == "unsubscribe_multi_timeframe":
                await get_multi_timeframe_runtime().unsubscribe_streams(client.client_id)
                # Drop mtf subscription markers
                client.subscriptions = {
                    s for s in client.subscriptions if not s.endswith(":mtf")
                }
                await self._send(
                    client,
                    MarketWsMessage(
                        type=WsMessageType.UNSUBSCRIBED,
                        status="ok",
                        detail="multi_timeframe",
                    ),
                )
                return

            if action == "subscribe_confluence":
                exchange = ExchangeId(payload["exchange"])
                market_type = MarketType(payload["market_type"])
                symbol = str(payload["symbol"])
                sub_key = f"{exchange.value}:{market_type.value}:{symbol.upper()}:confluence"
                client.subscriptions.add(sub_key)
                msg = await get_confluence_runtime().subscribe(
                    client.client_id,
                    exchange=exchange,
                    market_type=market_type,
                    symbol=symbol,
                )
                if msg is not None:
                    await self._send(client, msg)
                await self._send(
                    client,
                    MarketWsMessage(
                        type=WsMessageType.SUBSCRIBED,
                        exchange=exchange,
                        symbol=symbol,
                        market_type=market_type,
                        status="ok",
                        detail="confluence",
                    ),
                )
                return

            if action == "unsubscribe_confluence":
                get_confluence_runtime().unsubscribe_client(client.client_id)
                client.subscriptions = {
                    s for s in client.subscriptions if not s.endswith(":confluence")
                }
                await self._send(
                    client,
                    MarketWsMessage(
                        type=WsMessageType.UNSUBSCRIBED,
                        status="ok",
                        detail="confluence",
                    ),
                )
                return

            if action == "subscribe_trade_plan":
                exchange = ExchangeId(payload["exchange"])
                market_type = MarketType(payload["market_type"])
                symbol = str(payload["symbol"])
                account_balance = payload.get("account_balance")
                risk_percent = payload.get("risk_percent")
                sub_key = f"{exchange.value}:{market_type.value}:{symbol.upper()}:trade_plan"
                client.subscriptions.add(sub_key)
                msg = await get_trade_plan_runtime().subscribe(
                    client.client_id,
                    exchange=exchange,
                    market_type=market_type,
                    symbol=symbol,
                    account_balance=float(account_balance) if account_balance is not None else None,
                    risk_percent=float(risk_percent) if risk_percent is not None else None,
                )
                if msg is not None:
                    await self._send(client, msg)
                await self._send(
                    client,
                    MarketWsMessage(
                        type=WsMessageType.SUBSCRIBED,
                        exchange=exchange,
                        symbol=symbol,
                        market_type=market_type,
                        status="ok",
                        detail="trade_plan",
                    ),
                )
                return

            if action == "unsubscribe_trade_plan":
                get_trade_plan_runtime().unsubscribe_client(client.client_id)
                client.subscriptions = {
                    s for s in client.subscriptions if not s.endswith(":trade_plan")
                }
                await self._send(
                    client,
                    MarketWsMessage(
                        type=WsMessageType.UNSUBSCRIBED,
                        status="ok",
                        detail="trade_plan",
                    ),
                )
                return

            if action == "subscribe_decision":
                exchange = ExchangeId(payload["exchange"])
                market_type = MarketType(payload["market_type"])
                symbol = str(payload["symbol"])
                account_balance = payload.get("account_balance")
                risk_percent = payload.get("risk_percent")
                sub_key = f"{exchange.value}:{market_type.value}:{symbol.upper()}:decision"
                client.subscriptions.add(sub_key)
                msg = await get_decision_runtime().subscribe(
                    client.client_id,
                    exchange=exchange,
                    market_type=market_type,
                    symbol=symbol,
                    account_balance=float(account_balance) if account_balance is not None else None,
                    risk_percent=float(risk_percent) if risk_percent is not None else None,
                )
                if msg is not None:
                    await self._send(client, msg)
                await self._send(
                    client,
                    MarketWsMessage(
                        type=WsMessageType.SUBSCRIBED,
                        exchange=exchange,
                        symbol=symbol,
                        market_type=market_type,
                        status="ok",
                        detail="decision",
                    ),
                )
                return

            if action == "unsubscribe_decision":
                get_decision_runtime().unsubscribe_client(client.client_id)
                client.subscriptions = {
                    s for s in client.subscriptions if not s.endswith(":decision")
                }
                await self._send(
                    client,
                    MarketWsMessage(
                        type=WsMessageType.UNSUBSCRIBED,
                        status="ok",
                        detail="decision",
                    ),
                )
                return

            if action == "ping":
                await self._send(
                    client,
                    MarketWsMessage(type=WsMessageType.CONNECTION_STATUS, status="pong"),
                )
                return

            await self._send(
                client,
                MarketWsMessage(
                    type=WsMessageType.SUBSCRIPTION_ERROR,
                    status="error",
                    detail=f"Unknown action: {action}",
                ),
            )
        except Exception as exc:  # noqa: BLE001
            await self._send(
                client,
                MarketWsMessage(
                    type=WsMessageType.SUBSCRIPTION_ERROR,
                    status="error",
                    detail=str(exc),
                ),
            )


_ws_manager: WebsocketManager | None = None


def get_websocket_manager() -> WebsocketManager:
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebsocketManager()
    return _ws_manager
