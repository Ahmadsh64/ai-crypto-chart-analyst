"""Dedicated historical replay WebSocket hub (separate from live /ws/market)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from app.replay.manager import get_replay_manager

logger = logging.getLogger(__name__)


@dataclass
class ReplayClient:
    client_id: str
    websocket: WebSocket
    session_filter: str | None = None
    queue: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)


class ReplayWebsocketHub:
    def __init__(self) -> None:
        self._clients: dict[str, ReplayClient] = {}
        self._lock = asyncio.Lock()
        self._attached = False

    async def attach(self) -> None:
        if self._attached:
            return
        get_replay_manager().add_broadcaster(self.broadcast_event)
        self._attached = True

    async def broadcast_event(self, _event_type: str, body: dict[str, Any]) -> None:
        session_id = body.get("session_id")
        async with self._lock:
            clients = list(self._clients.values())
        for client in clients:
            if client.session_filter and client.session_filter != session_id:
                continue
            try:
                client.queue.put_nowait(body)
            except asyncio.QueueFull:
                logger.warning("Replay WS queue full for %s", client.client_id)

    async def handle_client(self, websocket: WebSocket) -> None:
        await self.attach()
        await websocket.accept()
        client = ReplayClient(client_id=str(uuid.uuid4()), websocket=websocket)
        async with self._lock:
            self._clients[client.client_id] = client
        await websocket.send_json(
            {
                "type": "replay_connected",
                "client_id": client.client_id,
                "detail": "Historical replay channel (not live market).",
            }
        )
        writer = asyncio.create_task(self._writer(client))
        try:
            while True:
                raw = await websocket.receive_json()
                await self._handle_message(client, raw)
        except WebSocketDisconnect:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.info("Replay WS closed: %s", exc)
        finally:
            writer.cancel()
            async with self._lock:
                self._clients.pop(client.client_id, None)

    async def _writer(self, client: ReplayClient) -> None:
        try:
            while True:
                msg = await client.queue.get()
                await client.websocket.send_json(msg)
        except asyncio.CancelledError:
            return
        except Exception:  # noqa: BLE001
            return

    async def _handle_message(self, client: ReplayClient, raw: dict[str, Any]) -> None:
        action = str(raw.get("action", "")).lower()
        if action == "ping":
            await client.websocket.send_json({"type": "pong"})
            return
        if action == "subscribe":
            sid = raw.get("session_id")
            client.session_filter = str(sid) if sid else None
            await client.websocket.send_json(
                {
                    "type": "replay_subscribed",
                    "session_id": client.session_filter,
                }
            )
            return
        if action == "unsubscribe":
            client.session_filter = None
            await client.websocket.send_json({"type": "replay_unsubscribed"})
            return
        await client.websocket.send_json(
            {"type": "replay_error", "error": f"Unknown action: {action}"}
        )


_hub: ReplayWebsocketHub | None = None


def get_replay_ws_hub() -> ReplayWebsocketHub:
    global _hub
    if _hub is None:
        _hub = ReplayWebsocketHub()
    return _hub
