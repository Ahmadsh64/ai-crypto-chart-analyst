"""REST schemas for confluence (Phase 4.2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.analysis.confluence.models import (
    CategoryScore,
    ConflictItem,
    ConfluenceDataQuality,
    EvidenceItem,
    PreliminaryAssessment,
)
from app.analysis.multi_timeframe.models import MultiTimeframeSnapshot
from app.exchanges.types import ExchangeId, MarketType


class ConfluenceResponse(BaseModel):
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    calculated_at: datetime
    data_source: str
    config: dict[str, Any]
    bullish_score: float
    bearish_score: float
    category_scores: list[CategoryScore] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    excluded_evidence: list[EvidenceItem] = Field(default_factory=list)
    conflicts: list[ConflictItem] = Field(default_factory=list)
    preliminary_assessment: PreliminaryAssessment
    assessment_strength: Literal["strong", "moderate", "none"] = "none"
    data_quality: ConfluenceDataQuality
    summary: str
    configuration_version: str
    analysis_timestamp: datetime
    mtf_snapshot: MultiTimeframeSnapshot | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
