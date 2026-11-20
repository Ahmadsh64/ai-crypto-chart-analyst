"""
Realtime Market Structure updates on closed candle changes.

Reuses the shared exchange stream — no extra WebSocket connections.
Recalculates on candle_update; emits only newly confirmed event keys.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.analysis.market_structure import analyze_market_structure, new_events_since
from app.analysis.market_structure.config import DEFAULT_STRUCTURE_CONFIG
from app.exchanges.manager import get_exchange_manager
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.market_data.ws_messages import CandleData, MarketWsMessage, WsMessageType

logger = logging.getLogger(__name__)


def _market_key(
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    timeframe: Timeframe,
) -> str:
    return f"{exchange.value}:{market_type.value}:{symbol.upper()}:{timeframe.value}"


@dataclass
class _SeriesState:
    candles: list[Candle] = field(default_factory=list)
    known_keys: set[str] = field(default_factory=set)
    last_payload_hash: str | None = None
    clients: set[str] = field(default_factory=set)
    last_closed_ts: datetime | None = None


class StructureRuntime:
    def __init__(self, max_candles: int = 500) -> None:
        self._series: dict[str, _SeriesState] = {}
        self._max_candles = max_candles

    async def subscribe(
        self,
        client_id: str,
        *,
        exchange: ExchangeId,
        market_type: MarketType,
        symbol: str,
        timeframe: Timeframe,
    ) -> MarketWsMessage:
        key = _market_key(exchange, market_type, symbol, timeframe)
        state = self._series.get(key)
        if state is None:
            candles = await get_exchange_manager().fetch_ohlcv(
                exchange,
                symbol,
                timeframe,
                market_type,
                limit=self._max_candles,
            )
            state = _SeriesState(candles=candles)
            self._series[key] = state
            # Seed known keys so we don't flood historical events as "new"
            result = analyze_market_structure(
                candles,
                exchange=exchange,
                symbol=symbol,
                market_type=market_type,
                timeframe=timeframe,
                config=DEFAULT_STRUCTURE_CONFIG,
                include_unconfirmed=False,
            )
            state.known_keys = set(result.event_keys)
            msg = self._snapshot_message(exchange, market_type, symbol, timeframe, result, force=True)
            state.clients.add(client_id)
            return msg

        state.clients.add(client_id)
        result = analyze_market_structure(
            state.candles,
            exchange=exchange,
            symbol=symbol,
            market_type=market_type,
            timeframe=timeframe,
            config=DEFAULT_STRUCTURE_CONFIG,
            include_unconfirmed=False,
        )
        return self._snapshot_message(exchange, market_type, symbol, timeframe, result, force=True)

    def unsubscribe_client(self, client_id: str) -> None:
        empty: list[str] = []
        for key, state in self._series.items():
            state.clients.discard(client_id)
            if not state.clients:
                empty.append(key)
        for key in empty:
            self._series.pop(key, None)

    async def on_market_message(self, message: MarketWsMessage) -> MarketWsMessage | None:
        if message.type != WsMessageType.CANDLE_UPDATE:
            return None
        if not (message.exchange and message.market_type and message.symbol and message.timeframe):
            return None

        if isinstance(message.data, CandleData):
            candle_data = message.data
        elif isinstance(message.data, dict):
            try:
                candle_data = CandleData.model_validate(message.data)
            except Exception:  # noqa: BLE001
                return None
        else:
            return None

        key = _market_key(message.exchange, message.market_type, message.symbol, message.timeframe)
        state = self._series.get(key)
        if state is None or not state.clients:
            return None

        candle = Candle(
            timestamp=candle_data.timestamp,
            open=candle_data.open,
            high=candle_data.high,
            low=candle_data.low,
            close=candle_data.close,
            volume=candle_data.volume,
            exchange=message.exchange,
            symbol=message.symbol.upper(),
            market_type=message.market_type,
            is_closed=candle_data.is_closed,
        )
        self._upsert_candle(state, candle)

        # Only emit confirmed structure updates when a candle closes (or pivot can confirm).
        # Forming ticks never create BOS/CHoCH/MSS.
        if not candle.is_closed:
            return None

        if state.last_closed_ts == candle.timestamp:
            # Same closed bar re-broadcast — still allow recompute once per unique hash
            pass
        state.last_closed_ts = candle.timestamp

        result = analyze_market_structure(
            state.candles,
            exchange=message.exchange,
            symbol=message.symbol,
            market_type=message.market_type,
            timeframe=message.timeframe,
            config=DEFAULT_STRUCTURE_CONFIG,
            include_unconfirmed=False,
        )
        fresh = new_events_since(state.known_keys, result)
        state.known_keys |= set(result.event_keys)

        has_new = any(fresh[k] for k in ("swings", "bos_events", "choch_events", "mss_events"))
        return self._update_message(
            message.exchange,
            message.market_type,
            message.symbol,
            message.timeframe,
            result,
            fresh,
            force=has_new,
        )

    def _upsert_candle(self, state: _SeriesState, candle: Candle) -> None:
        if state.candles and state.candles[-1].timestamp == candle.timestamp:
            state.candles[-1] = candle
        elif state.candles and candle.timestamp < state.candles[-1].timestamp:
            return
        else:
            state.candles.append(candle)
        if len(state.candles) > self._max_candles:
            state.candles = state.candles[-self._max_candles :]

    def _snapshot_message(
        self,
        exchange: ExchangeId,
        market_type: MarketType,
        symbol: str,
        timeframe: Timeframe,
        result,
        *,
        force: bool,
    ) -> MarketWsMessage | None:
        payload = {
            "kind": "snapshot",
            "config": result.config,
            "snapshot": result.snapshot.model_dump(mode="json"),
            "swings": [s.model_dump(mode="json") for s in result.swings],
            "bos_events": [e.model_dump(mode="json") for e in result.bos_events],
            "choch_events": [e.model_dump(mode="json") for e in result.choch_events],
            "mss_events": [e.model_dump(mode="json") for e in result.mss_events],
            "ambiguous_dual_breaks": [
                e.model_dump(mode="json") for e in result.ambiguous_dual_breaks
            ],
            "new_events": None,
        }
        digest = hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        key = _market_key(exchange, market_type, symbol, timeframe)
        state = self._series[key]
        if not force and digest == state.last_payload_hash:
            return None
        state.last_payload_hash = digest
        return MarketWsMessage(
            type=WsMessageType.STRUCTURE_UPDATE,
            exchange=exchange,
            symbol=symbol.upper(),
            market_type=market_type,
            timeframe=timeframe,
            exchange_ts=state.candles[-1].timestamp if state.candles else None,
            processed_at=datetime.now(timezone.utc),
            data=payload,
        )

    def _update_message(
        self,
        exchange: ExchangeId,
        market_type: MarketType,
        symbol: str,
        timeframe: Timeframe,
        result,
        fresh: dict,
        *,
        force: bool,
    ) -> MarketWsMessage | None:
        if not force:
            return None
        payload = {
            "kind": "update",
            "config": result.config,
            "snapshot": result.snapshot.model_dump(mode="json"),
            "swings": [s.model_dump(mode="json") for s in result.swings],
            "bos_events": [e.model_dump(mode="json") for e in result.bos_events],
            "choch_events": [e.model_dump(mode="json") for e in result.choch_events],
            "mss_events": [e.model_dump(mode="json") for e in result.mss_events],
            "ambiguous_dual_breaks": [
                e.model_dump(mode="json") for e in result.ambiguous_dual_breaks
            ],
            "new_events": {
                "swings": [s.model_dump(mode="json") for s in fresh["swings"]],
                "bos_events": [e.model_dump(mode="json") for e in fresh["bos_events"]],
                "choch_events": [e.model_dump(mode="json") for e in fresh["choch_events"]],
                "mss_events": [e.model_dump(mode="json") for e in fresh["mss_events"]],
                "ambiguous_dual_breaks": [
                    e.model_dump(mode="json") for e in fresh["ambiguous_dual_breaks"]
                ],
            },
        }
        return MarketWsMessage(
            type=WsMessageType.STRUCTURE_UPDATE,
            exchange=exchange,
            symbol=symbol.upper(),
            market_type=market_type,
            timeframe=timeframe,
            exchange_ts=result.snapshot.calculated_at,
            processed_at=datetime.now(timezone.utc),
            data=payload,
        )


_runtime: StructureRuntime | None = None


def get_structure_runtime() -> StructureRuntime:
    global _runtime
    if _runtime is None:
        _runtime = StructureRuntime()
    return _runtime
