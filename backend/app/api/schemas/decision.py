"""API schema for final decision responses (Phase 4.4)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.analysis.decision_engine.models import (
    ConfluenceScoreSummary,
    DecisionDataQuality,
    EntryConfirmationResult,
)
from app.exchanges.types import ExchangeId, MarketType


class DecisionResponse(BaseModel):
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    decision_id: str
    decision: str
    decision_reason: str
    direction: str | None = None
    lifecycle: str
    confluence_scores: ConfluenceScoreSummary
    trade_plan_status: str | None = None
    trade_plan_id: str | None = None
    entry_confirmation: EntryConfirmationResult
    entry_zone_summary: dict[str, Any] | None = None
    stop_loss_price: float | None = None
    take_profit_prices: list[float] = Field(default_factory=list)
    primary_rr: float | None = None
    risk_amount: float | None = None
    position_size: float | None = None
    price_inside_entry_zone: bool | None = None
    supporting_evidence: list[str] = Field(default_factory=list)
    blocking_conditions: list[str] = Field(default_factory=list)
    conflict_ids: list[str] = Field(default_factory=list)
    data_quality: DecisionDataQuality
    spot_restriction: str | None = None
    analysis_only_disclaimer: str
    configuration_version: str
    analysis_timestamp: datetime
    setup_detected_at: datetime | None = None
    expires_at: datetime | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    data_source: str
    metadata: dict[str, Any] = Field(default_factory=dict)
