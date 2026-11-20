"""Realtime confluence updates on confirmed ladder candle closes (Phase 4.2)."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.analysis.confluence.config import DEFAULT_CONFLUENCE_CONFIG
from app.analysis.multi_timeframe.config import MTF_LADDER
from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.market_data.ws_messages import CandleData, MarketWsMessage, WsMessageType
from app.services.confluence_service import compute_confluence_response

logger = logging.getLogger(__name__)


def _key(exchange: ExchangeId, market_type: MarketType, symbol: str) -> str:
    return f"{exchange.value}:{market_type.value}:{symbol.upper()}:confluence"


@dataclass
class _State:
    clients: set[str] = field(default_factory=set)
    last_payload_hash: str | None = None


class ConfluenceRuntime:
    def __init__(self) -> None:
        self._series: dict[str, _State] = {}

    async def subscribe(
        self,
        client_id: str,
        *,
        exchange: ExchangeId,
        market_type: MarketType,
        symbol: str,
    ) -> MarketWsMessage:
        key = _key(exchange, market_type, symbol)
        state = self._series.get(key)
        if state is None:
            state = _State()
            self._series[key] = state
        state.clients.add(client_id)
        response = await compute_confluence_response(
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
        )
        return self._message(exchange, market_type, symbol, response, kind="snapshot", force=True)

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
        if not message.exchange or not message.symbol or not message.market_type:
            return None
        if message.timeframe is None or message.timeframe not in MTF_LADDER:
            return None
        data = message.data
        if not isinstance(data, CandleData) or not data.is_closed:
            # Forming candles must not trigger a directional reassessment.
            return None

        key = _key(message.exchange, message.market_type, message.symbol)
        state = self._series.get(key)
        if state is None or not state.clients:
            return None

        try:
            response = await compute_confluence_response(
                exchange=message.exchange,
                market_type=message.market_type,
                symbol=message.symbol,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Confluence recompute failed: %s", exc)
            return None

        return self._message(
            message.exchange,
            message.market_type,
            message.symbol,
            response,
            kind="update",
            force=False,
        )

    def _message(
        self,
        exchange: ExchangeId,
        market_type: MarketType,
        symbol: str,
        response,
        *,
        kind: str,
        force: bool,
    ) -> MarketWsMessage | None:
        payload = {
            "kind": kind,
            "config": response.config,
            "bullish_score": response.bullish_score,
            "bearish_score": response.bearish_score,
            "category_scores": [c.model_dump(mode="json") for c in response.category_scores],
            "evidence": [e.model_dump(mode="json") for e in response.evidence],
            "excluded_evidence": [
                e.model_dump(mode="json") for e in response.excluded_evidence
            ],
            "conflicts": [c.model_dump(mode="json") for c in response.conflicts],
            "preliminary_assessment": response.preliminary_assessment.value,
            "assessment_strength": response.assessment_strength,
            "data_quality": response.data_quality.model_dump(mode="json"),
            "summary": response.summary,
            "configuration_version": response.configuration_version,
            "analysis_timestamp": response.analysis_timestamp.isoformat(),
            "metadata": response.metadata,
        }
        digest = hashlib.sha1(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()
        key = _key(exchange, market_type, symbol)
        state = self._series.get(key)
        if state is not None and not force and digest == state.last_payload_hash:
            return None
        if state is not None:
            state.last_payload_hash = digest
        return MarketWsMessage(
            type=WsMessageType.CONFLUENCE_UPDATE,
            exchange=exchange,
            symbol=symbol,
            market_type=market_type,
            exchange_ts=response.analysis_timestamp,
            processed_at=datetime.now(timezone.utc),
            data=payload,
        )


_runtime: ConfluenceRuntime | None = None


def get_confluence_runtime() -> ConfluenceRuntime:
    global _runtime
    if _runtime is None:
        _runtime = ConfluenceRuntime()
    return _runtime
