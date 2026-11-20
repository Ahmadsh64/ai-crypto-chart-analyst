"""Typed trade-plan models (Phase 4.3)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.exchanges.types import ExchangeId, MarketType
from app.analysis.trade_plan.config import EntryType, PlanDirection, PlanStatus


class PlanDirectionEnum(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class PlanStatusEnum(str, Enum):
    ELIGIBLE = "eligible"
    BLOCKED = "blocked"
    INVALID = "invalid"


class EntryZone(BaseModel):
    entry_low: float
    entry_high: float
    entry_reference_price: float
    entry_type: EntryType
    entry_source: str
    source_event_key: str
    timeframe: str
    entry_explanation: str
    price_inside_zone: bool = False


class StopLossPlan(BaseModel):
    stop_loss_price: float
    stop_loss_source: str
    stop_loss_distance: float
    stop_loss_distance_pct: float
    atr_value: float | None = None
    buffer_value: float
    invalidation_explanation: str
    source_event_key: str | None = None


class TakeProfitTarget(BaseModel):
    index: int = Field(ge=1, le=5)
    label: str  # TP1 / TP2 / TP3
    price: float
    source: str
    source_event_key: str | None = None
    distance: float
    distance_pct: float
    risk_reward_ratio: float
    explanation: str


class RiskMetrics(BaseModel):
    risk_distance: float
    risk_distance_pct: float
    reward_distances: list[float] = Field(default_factory=list)
    primary_rr: float | None = None
    minimum_required_rr: float
    meets_minimum_rr: bool


class PositionSizing(BaseModel):
    account_balance: float
    risk_percent: float
    risk_amount: float
    position_size: float | None = None
    position_notional: float | None = None
    estimated_loss_at_sl: float | None = None
    contract_multiplier: float | None = None
    sizing_available: bool
    sizing_explanation: str
    is_hypothetical: bool = True


class ValidationResult(BaseModel):
    is_valid: bool
    validation_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)


class EligibilityResult(BaseModel):
    is_eligible: bool
    direction: PlanDirection | None = None
    blocking_reasons: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class TradePlanDataQuality(BaseModel):
    overall: str
    is_analysis_complete: bool
    timeframes_used: list[str] = Field(default_factory=list)
    timeframes_unavailable: list[str] = Field(default_factory=list)
    timeframes_stale: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    current_price: float | None = None
    atr_available: bool = False


class TradePlanResult(BaseModel):
    plan_id: str
    symbol: str
    exchange: ExchangeId
    market_type: MarketType
    direction: PlanDirection | None = None
    plan_status: PlanStatus
    entry: EntryZone | None = None
    stop_loss: StopLossPlan | None = None
    take_profit_targets: list[TakeProfitTarget] = Field(default_factory=list)
    risk: RiskMetrics | None = None
    position_sizing: PositionSizing | None = None
    validation: ValidationResult
    eligibility: EligibilityResult
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    conflict_ids: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    explanations: list[str] = Field(default_factory=list)
    configuration_version: str
    analysis_timestamp: datetime
    data_quality: TradePlanDataQuality
    confluence_assessment: str | None = None
    confluence_assessment_strength: str | None = None
    bullish_score: float | None = None
    bearish_score: float | None = None
    spot_short_warning: str | None = None
    analysis_only_disclaimer: str = (
        "Analysis only — no orders are executed. Prices are analytical levels, not guaranteed fills."
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
