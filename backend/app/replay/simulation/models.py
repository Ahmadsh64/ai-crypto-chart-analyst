"""Historical trade simulation models (Phase 5.2.2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.exchanges.types import ExchangeId, MarketType
from app.replay.simulation.enums import (
    SimulationEventType,
    TradeDirection,
    TradeLifecycleStatus,
)


class SimulationExecutionEvent(BaseModel):
    event_id: str
    event_type: SimulationEventType
    timestamp: datetime
    price: float | None = None
    quantity: float | None = None
    remaining_quantity: float | None = None
    tp_index: int | None = None
    reason: str | None = None
    ambiguity_policy_applied: str | None = None
    candle_open_time: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SimulatedTrade(BaseModel):
    trade_id: str
    signal_key: str
    replay_session_id: str
    signal_id: str | None = None
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    direction: TradeDirection
    decision: str
    decision_timestamp: datetime
    decision_event_index: int
    lifecycle_status: TradeLifecycleStatus

    entry_zone: dict[str, Any] | None = None
    entry_limit_price: float | None = None
    entry_price: float | None = None
    entry_timestamp: datetime | None = None
    exit_timestamp: datetime | None = None

    initial_stop_loss: float
    current_stop_loss: float
    take_profit_levels: list[float] = Field(default_factory=list)
    tp_allocations: list[float] = Field(default_factory=list)
    tp_filled: list[bool] = Field(default_factory=list)

    original_quantity: float
    remaining_quantity: float
    executed_quantity: float = 0.0
    quantity_closed_tp: float = 0.0
    quantity_closed_sl: float = 0.0
    quantity_closed_expired: float = 0.0

    expires_at: datetime | None = None
    rejection_reason: str | None = None
    ambiguity_warnings: list[str] = Field(default_factory=list)
    realized_pnl_placeholder: Literal[None] = None
    """Intentionally null — P&L belongs to Phase 5.2.3/5.2.4."""

    risk_reward: float | None = None
    decision_reason: str | None = None
    execution_events: list[SimulationExecutionEvent] = Field(default_factory=list)
    config_version: str
    created_at: datetime
    updated_at: datetime


class SimulationOverview(BaseModel):
    enabled: bool
    pending_count: int = 0
    open_count: int = 0
    partially_closed_count: int = 0
    closed_count: int = 0
    rejected_count: int = 0
    cancelled_count: int = 0
    ambiguous_count: int = 0
    total_trades: int = 0
    config: dict[str, Any] = Field(default_factory=dict)
    disclaimer: str
    replay_timestamp: datetime | None = None


class SimulationSnapshot(BaseModel):
    session_id: str
    enabled: bool
    overview: SimulationOverview
    trades: list[SimulatedTrade] = Field(default_factory=list)
    recent_events: list[SimulationExecutionEvent] = Field(default_factory=list)
    config_version: str
    disclaimer: str
