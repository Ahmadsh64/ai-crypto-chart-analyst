"""Typed final-decision models (Phase 4.4)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.exchanges.types import ExchangeId, MarketType
from app.analysis.decision_engine.config import (
    EntryConfirmationStatus,
    FinalDecision,
    SetupLifecycle,
)


class ConfluenceScoreSummary(BaseModel):
    bullish_score: float
    bearish_score: float
    preliminary_assessment: str | None = None
    assessment_strength: str | None = None


class EntryConfirmationResult(BaseModel):
    status: EntryConfirmationStatus
    is_confirmed: bool = False
    confirmation_type: str | None = None
    source_event_key: str | None = None
    timeframe: str | None = None
    direction: str | None = None
    explanation: str
    evidence_ids: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)


class DecisionEligibilityResult(BaseModel):
    is_setup_valid: bool
    direction: str | None = None
    blocking_reasons: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DecisionDataQuality(BaseModel):
    overall: str
    is_analysis_complete: bool
    timeframes_used: list[str] = Field(default_factory=list)
    timeframes_unavailable: list[str] = Field(default_factory=list)
    timeframes_stale: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    current_price: float | None = None


class DecisionResult(BaseModel):
    decision_id: str
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    decision: FinalDecision
    decision_reason: str
    direction: str | None = None
    lifecycle: SetupLifecycle
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
    analysis_only_disclaimer: str = (
        "Analysis only — no orders are executed. Analytical conditions do not "
        "guarantee execution or profit."
    )
    configuration_version: str
    analysis_timestamp: datetime
    setup_detected_at: datetime | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
