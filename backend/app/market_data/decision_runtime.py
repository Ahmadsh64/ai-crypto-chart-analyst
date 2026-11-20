"""Realtime decision updates on confirmed ladder candle closes (Phase 4.4)."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.analysis.multi_timeframe.config import MTF_LADDER
from app.exchanges.types import ExchangeId, MarketType
from app.market_data.ws_messages import CandleData, MarketWsMessage, WsMessageType
from app.services.decision_service import compute_decision_response

logger = logging.getLogger(__name__)


def _key(exchange: ExchangeId, market_type: MarketType, symbol: str) -> str:
    return f"{exchange.value}:{market_type.value}:{symbol.upper()}:decision"


@dataclass
class _Prefs:
    account_balance: float | None = None
    risk_percent: float | None = None


@dataclass
class _State:
    clients: dict[str, _Prefs] = field(default_factory=dict)
    last_payload_hash: str | None = None


class DecisionRuntime:
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
        state.clients[client_id] = _Prefs(account_balance, risk_percent)
        response = await compute_decision_response(
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

        prefs = next(iter(state.clients.values()))
        try:
            response = await compute_decision_response(
                exchange=message.exchange,
                market_type=message.market_type,
                symbol=message.symbol,
                account_balance=prefs.account_balance,
                risk_percent=prefs.risk_percent,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Decision recompute failed: %s", exc)
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
            "decision_id": response.decision_id,
            "decision": response.decision,
            "decision_reason": response.decision_reason,
            "direction": response.direction,
            "lifecycle": response.lifecycle,
            "confluence_scores": response.confluence_scores.model_dump(mode="json"),
            "trade_plan_status": response.trade_plan_status,
            "trade_plan_id": response.trade_plan_id,
            "entry_confirmation": response.entry_confirmation.model_dump(mode="json"),
            "entry_zone_summary": response.entry_zone_summary,
            "stop_loss_price": response.stop_loss_price,
            "take_profit_prices": response.take_profit_prices,
            "primary_rr": response.primary_rr,
            "risk_amount": response.risk_amount,
            "position_size": response.position_size,
            "price_inside_entry_zone": response.price_inside_entry_zone,
            "supporting_evidence": response.supporting_evidence,
            "blocking_conditions": response.blocking_conditions,
            "conflict_ids": response.conflict_ids,
            "data_quality": response.data_quality.model_dump(mode="json"),
            "spot_restriction": response.spot_restriction,
            "analysis_only_disclaimer": response.analysis_only_disclaimer,
            "configuration_version": response.configuration_version,
            "analysis_timestamp": response.analysis_timestamp.isoformat(),
            "setup_detected_at": (
                response.setup_detected_at.isoformat() if response.setup_detected_at else None
            ),
            "expires_at": response.expires_at.isoformat() if response.expires_at else None,
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
            type=WsMessageType.DECISION_UPDATE,
            exchange=exchange,
            symbol=symbol,
            market_type=market_type,
            exchange_ts=response.analysis_timestamp,
            processed_at=datetime.now(timezone.utc),
            data=payload,
        )


_runtime: DecisionRuntime | None = None


def get_decision_runtime() -> DecisionRuntime:
    global _runtime
    if _runtime is None:
        _runtime = DecisionRuntime()
    return _runtime
