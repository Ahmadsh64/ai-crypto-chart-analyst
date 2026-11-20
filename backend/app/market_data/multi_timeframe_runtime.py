"""Realtime Multi-Timeframe orchestration updates (Phase 4.1)."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.analysis.multi_timeframe.config import DEFAULT_MTF_CONFIG, MultiTimeframeConfig
from app.market_data.normalizer import to_internal_symbol
from app.analysis.multi_timeframe.orchestrator import (
    apply_candle_update,
    build_snapshot,
    evaluate_timeframe_series,
)
from app.exchanges.manager import get_exchange_manager
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.market_data.stream_manager import get_stream_manager
from app.market_data.ws_messages import CandleData, MarketWsMessage, WsMessageType

logger = logging.getLogger(__name__)


def _market_key(exchange: ExchangeId, market_type: MarketType, symbol: str) -> str:
    return f"{exchange.value}:{market_type.value}:{symbol.upper()}:mtf"


@dataclass
class _MtfState:
    candles: dict[Timeframe, list[Candle]] = field(default_factory=dict)
    clients: set[str] = field(default_factory=set)
    last_payload_hash: str | None = None
    # client_id -> stream topic keys subscribed for MTF ladder
    client_stream_keys: dict[str, set[str]] = field(default_factory=dict)


class MultiTimeframeRuntime:
    def __init__(self, config: MultiTimeframeConfig | None = None) -> None:
        self._config = config or DEFAULT_MTF_CONFIG
        self._series: dict[str, _MtfState] = {}

    async def subscribe(
        self,
        client_id: str,
        *,
        exchange: ExchangeId,
        market_type: MarketType,
        symbol: str,
    ) -> MarketWsMessage:
        key = _market_key(exchange, market_type, symbol)
        state = self._series.get(key)
        if state is None:
            state = _MtfState()
            self._series[key] = state
            for tf in self._config.timeframes:
                limit = self._config.history_for(tf).fetch_limit
                try:
                    candles = await get_exchange_manager().fetch_ohlcv(
                        exchange,
                        symbol,
                        tf,
                        market_type,
                        limit=limit,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("MTF seed failed %s %s: %s", symbol, tf.value, exc)
                    candles = []
                state.candles[tf] = candles

        state.clients.add(client_id)

        # Ensure exchange kline streams for all ladder TFs (same connection).
        stream_keys: set[str] = set()
        sm = get_stream_manager()
        for tf in self._config.timeframes:
            topic = await sm.subscribe(
                f"{client_id}:mtf:{tf.value}",
                exchange=exchange,
                market_type=market_type,
                symbol=symbol,
                timeframe=tf,
            )
            stream_keys.add(topic.key)
        state.client_stream_keys[client_id] = stream_keys

        snapshot = self._build(exchange, market_type, symbol, state)
        return self._message(
            exchange,
            market_type,
            symbol,
            snapshot,
            kind="snapshot",
            force=True,
            confirmed_candle=None,
            forming_candle=None,
            updated_timeframe=None,
        )

    def unsubscribe_client(self, client_id: str) -> None:
        empty: list[str] = []
        for key, state in self._series.items():
            if client_id in state.clients:
                state.clients.discard(client_id)
                state.client_stream_keys.pop(client_id, None)
            if not state.clients:
                empty.append(key)
        for key in empty:
            self._series.pop(key, None)

    async def unsubscribe_streams(self, client_id: str) -> None:
        """Drop MTF-owned stream refcounts (call on client disconnect / unsub)."""
        sm = get_stream_manager()
        for state in self._series.values():
            keys = state.client_stream_keys.get(client_id) or set()
            for topic_key in keys:
                # topic_key = exchange:market:SYMBOL:tf
                parts = topic_key.split(":")
                if len(parts) < 4:
                    continue
                try:
                    exchange = ExchangeId(parts[0])
                    market_type = MarketType(parts[1])
                    symbol = parts[2]
                    tf = Timeframe(parts[3])
                except ValueError:
                    continue
                await sm.unsubscribe(
                    f"{client_id}:mtf:{tf.value}",
                    exchange=exchange,
                    market_type=market_type,
                    symbol=symbol,
                    timeframe=tf,
                )
        self.unsubscribe_client(client_id)

    async def on_market_message(self, message: MarketWsMessage) -> MarketWsMessage | None:
        if message.type != WsMessageType.CANDLE_UPDATE:
            return None
        if not message.exchange or not message.symbol or not message.market_type:
            return None
        if message.timeframe is None or message.timeframe not in self._config.timeframes:
            return None
        data = message.data
        if not isinstance(data, CandleData):
            return None

        key = _market_key(message.exchange, message.market_type, message.symbol)
        state = self._series.get(key)
        if state is None or not state.clients:
            return None

        sym = to_internal_symbol(message.symbol)
        for candles in state.candles.values():
            if candles:
                sym = candles[0].symbol
                break
        candle = Candle(
            timestamp=data.timestamp,
            open=data.open,
            high=data.high,
            low=data.low,
            close=data.close,
            volume=data.volume,
            exchange=message.exchange,
            symbol=sym,
            market_type=message.market_type,
            is_closed=data.is_closed,
        )

        tf = message.timeframe
        limit = self._config.history_for(tf).fetch_limit
        series = state.candles.get(tf, [])
        state.candles[tf] = apply_candle_update(series, candle, max_candles=limit)

        snapshot = self._build(
            message.exchange, message.market_type, message.symbol, state
        )
        confirmed = candle if candle.is_closed else None
        forming = candle if not candle.is_closed else None
        return self._message(
            message.exchange,
            message.market_type,
            message.symbol,
            snapshot,
            kind="update",
            force=True,
            confirmed_candle=confirmed,
            forming_candle=forming,
            updated_timeframe=tf,
        )

    def _build(
        self,
        exchange: ExchangeId,
        market_type: MarketType,
        symbol: str,
        state: _MtfState,
    ):
        # Prefer internal slash symbol from seeded candles
        sym = symbol
        for candles in state.candles.values():
            if candles:
                sym = candles[0].symbol
                break
        series = {}
        now = datetime.now(timezone.utc)
        for tf in self._config.timeframes:
            series[tf] = evaluate_timeframe_series(
                state.candles.get(tf, []),
                timeframe=tf,
                exchange=exchange,
                symbol=sym,
                market_type=market_type,
                as_of=now,
                config=self._config,
                error=None if tf in state.candles else "Not seeded",
            )
        return build_snapshot(
            series,
            exchange=exchange,
            symbol=sym,
            market_type=market_type,
            as_of=now,
            config=self._config,
        )

    def _message(
        self,
        exchange: ExchangeId,
        market_type: MarketType,
        symbol: str,
        snapshot,
        *,
        kind: str,
        force: bool,
        confirmed_candle: Candle | None,
        forming_candle: Candle | None,
        updated_timeframe: Timeframe | None,
    ) -> MarketWsMessage | None:
        payload = {
            "kind": kind,
            "config": self._config.snapshot(),
            "snapshot": snapshot.model_dump(mode="json"),
            "timeframes": [t.model_dump(mode="json") for t in snapshot.timeframes],
            "sync": snapshot.sync.model_dump(mode="json"),
            "updated_timeframe": updated_timeframe.value if updated_timeframe else None,
            "confirmed_candle": (
                confirmed_candle.model_dump(mode="json") if confirmed_candle else None
            ),
            "forming_candle": (
                forming_candle.model_dump(mode="json") if forming_candle else None
            ),
        }
        digest = hashlib.sha1(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()
        key = _market_key(exchange, market_type, symbol)
        state = self._series.get(key)
        if state is not None and not force and digest == state.last_payload_hash:
            return None
        if state is not None:
            state.last_payload_hash = digest

        return MarketWsMessage(
            type=WsMessageType.MULTI_TIMEFRAME_UPDATE,
            exchange=exchange,
            symbol=symbol.upper() if "/" not in (symbol or "") else symbol,
            market_type=market_type,
            timeframe=updated_timeframe,
            exchange_ts=snapshot.calculated_at,
            processed_at=datetime.now(timezone.utc),
            data=payload,
        )


_runtime: MultiTimeframeRuntime | None = None


def get_multi_timeframe_runtime() -> MultiTimeframeRuntime:
    global _runtime
    if _runtime is None:
        _runtime = MultiTimeframeRuntime()
    return _runtime
