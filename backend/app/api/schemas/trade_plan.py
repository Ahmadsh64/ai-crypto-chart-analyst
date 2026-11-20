"""API schema for trade-plan responses (Phase 4.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.analysis.trade_plan.models import (
    EligibilityResult,
    EntryZone,
    PositionSizing,
    RiskMetrics,
    StopLossPlan,
    TakeProfitTarget,
    TradePlanDataQuality,
    ValidationResult,
)
from app.exchanges.types import ExchangeId, MarketType


class TradePlanResponse(BaseModel):
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    plan_id: str
    direction: str | None = None
    plan_status: str
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
    analysis_only_disclaimer: str
    config: dict[str, Any] = Field(default_factory=dict)
    data_source: str
    metadata: dict[str, Any] = Field(default_factory=dict)
