"""In-memory replay session registry (Phase 5.1)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.replay.config import ReplayConfig, ReplaySpeed
from app.replay.session import ReplaySession

logger = logging.getLogger(__name__)


class ReplayManager:
    """Process-local session store — no Redis/Postgres required."""

    def __init__(self) -> None:
        self._sessions: dict[str, ReplaySession] = {}
        self._lock = asyncio.Lock()
        self._broadcasters: list = []

    def add_broadcaster(self, fn) -> None:
        if fn not in self._broadcasters:
            self._broadcasters.append(fn)

    def remove_broadcaster(self, fn) -> None:
        if fn in self._broadcasters:
            self._broadcasters.remove(fn)

    async def _broadcast(self, event_type: str, body: dict) -> None:
        for fn in list(self._broadcasters):
            try:
                await fn(event_type, body)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Replay broadcaster error: %s", exc)

    async def create_session(
        self,
        *,
        exchange: ExchangeId,
        symbol: str,
        market_type: MarketType,
        start_time: datetime,
        end_time: datetime,
        timeframes: tuple[Timeframe, ...] | None = None,
        speed: ReplaySpeed | None = None,
        config: ReplayConfig | None = None,
        load: bool = True,
    ) -> ReplaySession:
        session = ReplaySession(
            exchange=exchange,
            symbol=symbol,
            market_type=market_type,
            start_time=start_time,
            end_time=end_time,
            timeframes=timeframes,
            config=config,
            on_event=self._broadcast,
        )
        if speed is not None:
            session.speed = speed
        async with self._lock:
            self._sessions[session.session_id] = session
        if load:
            await session.load()
        return session

    def get(self, session_id: str) -> ReplaySession | None:
        return self._sessions.get(session_id)

    def require(self, session_id: str) -> ReplaySession:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(session_id)
        return session

    async def delete(self, session_id: str) -> bool:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        try:
            await session.stop()
        except Exception:  # noqa: BLE001
            pass
        return True

    def list_ids(self) -> list[str]:
        return list(self._sessions.keys())


_manager: ReplayManager | None = None


def get_replay_manager() -> ReplayManager:
    global _manager
    if _manager is None:
        _manager = ReplayManager()
    return _manager


def reset_replay_manager() -> None:
    """Test helper — drop the singleton."""
    global _manager
    _manager = ReplayManager()
