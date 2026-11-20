"""Realtime trade-plan updates on confirmed ladder candle closes (Phase 4.3)."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.analysis.multi_timeframe.config import MTF_LADDER
from app.analysis.trade_plan.config import DEFAULT_TRADE_PLAN_CONFIG
from app.exchanges.types import ExchangeId, MarketType
from app.market_data.ws_messages import CandleData, MarketWsMessage, WsMessageType
from app.services.trade_plan_service import compute_trade_plan_response

logger = logging.getLogger(__name__)


def _key(exchange: ExchangeId, market_type: MarketType, symbol: str) -> str:
    return f"{exchange.value}:{market_type.value}:{symbol.upper()}:trade_plan"


@dataclass
class _ClientPrefs:
    account_balance: float | None = None
    risk_percent: float | None = None


@dataclass
class _State:
    clients: dict[str, _ClientPrefs] = field(default_factory=dict)
    last_payload_hash: str | None = None


class TradePlanRuntime:
    def __init__(self) -> None:
        self._series: dict[str, _State] = {}

    async def subscribe(
        self,
        client_id: str,
        *,
        exchange: ExchangeId,
        market_type: MarketType,
        symbol: str,
        account_balance: float | None = None,
        risk_percent: float | None = None,
    ) -> MarketWsMessage:
        key = _key(exchange, market_type, symbol)
        state = self._series.get(key)
        if state is None:
            state = _State()
            self._series[key] = state
        state.clients[client_id] = _ClientPrefs(
            account_balance=account_balance,
            risk_percent=risk_percent,
        )
        response = await compute_trade_plan_response(
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
            account_balance=account_balance,
            risk_percent=risk_percent,
        )
        return self._message(exchange, market_type, symbol, response, kind="snapshot", force=True)

    def unsubscribe_client(self, client_id: str) -> None:
        empty: list[str] = []
        for key, state in self._series.items():
            state.clients.pop(client_id, None)
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
            return None

        key = _key(message.exchange, message.market_type, message.symbol)
        state = self._series.get(key)
        if state is None or not state.clients:
            return None

        # Use first subscriber prefs (virtual sizing is client-local; snapshot uses defaults)
        prefs = next(iter(state.clients.values()))
        try:
            response = await compute_trade_plan_response(
                exchange=message.exchange,
                market_type=message.market_type,
                symbol=message.symbol,
                account_balance=prefs.account_balance,
                risk_percent=prefs.risk_percent,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Trade plan recompute failed: %s", exc)
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
            "plan_id": response.plan_id,
            "direction": response.direction,
            "plan_status": response.plan_status,
            "entry": response.entry.model_dump(mode="json") if response.entry else None,
            "stop_loss": response.stop_loss.model_dump(mode="json") if response.stop_loss else None,
            "take_profit_targets": [
                t.model_dump(mode="json") for t in response.take_profit_targets
            ],
            "risk": response.risk.model_dump(mode="json") if response.risk else None,
            "position_sizing": (
                response.position_sizing.model_dump(mode="json")
                if response.position_sizing
                else None
            ),
            "validation": response.validation.model_dump(mode="json"),
            "eligibility": response.eligibility.model_dump(mode="json"),
            "supporting_evidence_ids": response.supporting_evidence_ids,
            "conflict_ids": response.conflict_ids,
            "invalidation_conditions": response.invalidation_conditions,
            "explanations": response.explanations,
            "configuration_version": response.configuration_version,
            "analysis_timestamp": response.analysis_timestamp.isoformat(),
            "data_quality": response.data_quality.model_dump(mode="json"),
            "confluence_assessment": response.confluence_assessment,
            "confluence_assessment_strength": response.confluence_assessment_strength,
            "bullish_score": response.bullish_score,
            "bearish_score": response.bearish_score,
            "spot_short_warning": response.spot_short_warning,
            "analysis_only_disclaimer": response.analysis_only_disclaimer,
            "config": response.config,
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
            type=WsMessageType.TRADE_PLAN_UPDATE,
            exchange=exchange,
            symbol=symbol,
            market_type=market_type,
            exchange_ts=response.analysis_timestamp,
            processed_at=datetime.now(timezone.utc),
            data=payload,
        )


_runtime: TradePlanRuntime | None = None


def get_trade_plan_runtime() -> TradePlanRuntime:
    global _runtime
    if _runtime is None:
        _runtime = TradePlanRuntime()
    return _runtime
