"""
Realtime indicator recalculation on candle updates.

Uses the shared exchange stream (no extra exchange WebSocket).
Caches recent OHLCV per market key and recomputes latest indicator values
only when a candle_update arrives.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.analysis.indicators.calculator import calculate_indicators, round_latest_for_api
from app.analysis.indicators.models import DEFAULT_INDICATORS, IndicatorId
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
    indicator_ids: set[IndicatorId] = field(default_factory=set)
    last_payload_hash: str | None = None
    clients: set[str] = field(default_factory=set)


class IndicatorRuntime:
    def __init__(self, max_candles: int = 400) -> None:
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
        indicator_ids: list[IndicatorId] | None = None,
    ) -> MarketWsMessage:
        key = _market_key(exchange, market_type, symbol, timeframe)
        state = self._series.get(key)
        ids = set(indicator_ids or DEFAULT_INDICATORS)
        if state is None:
            candles = await get_exchange_manager().fetch_ohlcv(
                exchange,
                symbol,
                timeframe,
                market_type,
                limit=self._max_candles,
            )
            state = _SeriesState(candles=candles, indicator_ids=ids)
            self._series[key] = state
        else:
            state.indicator_ids |= ids
        state.clients.add(client_id)
        return self._build_message(exchange, market_type, symbol, timeframe, state, force=True)

    def unsubscribe_client(self, client_id: str) -> None:
        empty_keys: list[str] = []
        for key, state in self._series.items():
            state.clients.discard(client_id)
            if not state.clients:
                empty_keys.append(key)
        for key in empty_keys:
            self._series.pop(key, None)

    async def on_market_message(self, message: MarketWsMessage) -> MarketWsMessage | None:
        if message.type != WsMessageType.CANDLE_UPDATE:
            return None
        if not (message.exchange and message.market_type and message.symbol and message.timeframe):
            return None
        if not isinstance(message.data, CandleData):
            # data may be dict after JSON round-trip internally — handle both
            data = message.data
            if isinstance(data, dict):
                try:
                    candle_data = CandleData.model_validate(data)
                except Exception:  # noqa: BLE001
                    return None
            else:
                return None
        else:
            candle_data = message.data

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
        return self._build_message(
            message.exchange,
            message.market_type,
            message.symbol,
            message.timeframe,
            state,
            force=False,
        )

    def _upsert_candle(self, state: _SeriesState, candle: Candle) -> None:
        if state.candles and state.candles[-1].timestamp == candle.timestamp:
            state.candles[-1] = candle
        elif state.candles and candle.timestamp < state.candles[-1].timestamp:
            # Ignore out-of-order updates to prevent look-ahead / corruption.
            return
        else:
            state.candles.append(candle)
        if len(state.candles) > self._max_candles:
            state.candles = state.candles[-self._max_candles :]

    def _build_message(
        self,
        exchange: ExchangeId,
        market_type: MarketType,
        symbol: str,
        timeframe: Timeframe,
        state: _SeriesState,
        *,
        force: bool,
    ) -> MarketWsMessage | None:
        # Closed-candle analytics by default; include forming when last bar is open.
        include_forming = bool(state.candles and not state.candles[-1].is_closed)
        bundle = calculate_indicators(
            state.candles,
            indicators=sorted(state.indicator_ids, key=lambda i: i.value),
            include_forming=include_forming,
            include_series=False,
        )
        latest = {k: round_latest_for_api(v).model_dump(mode="json") for k, v in bundle.latest.items()}
        payload = {
            "include_forming": include_forming,
            "closed_candles_used": bundle.closed_candles_used,
            "indicators": latest,
        }
        digest = hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        if not force and digest == state.last_payload_hash:
            return None
        state.last_payload_hash = digest
        return MarketWsMessage(
            type=WsMessageType.INDICATOR_UPDATE,
            exchange=exchange,
            symbol=symbol.upper(),
            market_type=market_type,
            timeframe=timeframe,
            exchange_ts=state.candles[-1].timestamp if state.candles else None,
            processed_at=datetime.now(timezone.utc),
            data=payload,
        )


_runtime: IndicatorRuntime | None = None


def get_indicator_runtime() -> IndicatorRuntime:
    global _runtime
    if _runtime is None:
        _runtime = IndicatorRuntime()
    return _runtime
