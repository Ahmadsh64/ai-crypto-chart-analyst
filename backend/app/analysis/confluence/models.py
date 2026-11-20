"""Confluence evidence, conflict, and result models (Phase 4.2)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.exchanges.types import ExchangeId, MarketType, Timeframe


class EvidenceDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class EvidenceType(str, Enum):
    STRUCTURE_BIAS = "structure_bias"
    MSS = "mss"
    BOS = "bos"
    CHOCH = "choch"
    SWING_LABELS = "swing_labels"
    LIQUIDITY_SWEEP = "liquidity_sweep"
    LIQUIDITY_LEVEL = "liquidity_level"
    ORDER_BLOCK = "order_block"
    FVG = "fvg"


class ConflictSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PreliminaryAssessment(str, Enum):
    BULLISH_CONFLUENCE = "bullish_confluence"
    BEARISH_CONFLUENCE = "bearish_confluence"
    MIXED = "mixed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    DATA_UNAVAILABLE = "data_unavailable"


class EvidenceItem(BaseModel):
    evidence_id: str
    evidence_type: EvidenceType
    category: str
    timeframe: Timeframe
    direction: EvidenceDirection
    strength: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    source_event_key: str
    source_timestamp: datetime | None = None
    is_confirmed: bool = True
    is_active: bool = True
    explanation: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    excluded: bool = False
    exclusion_reason: str | None = None

    @property
    def dedupe_key(self) -> str:
        return f"{self.category}:{self.timeframe.value}:{self.source_event_key}"


class ConflictItem(BaseModel):
    conflict_type: str
    severity: ConflictSeverity
    affected_timeframes: list[Timeframe] = Field(default_factory=list)
    bullish_evidence_ids: list[str] = Field(default_factory=list)
    bearish_evidence_ids: list[str] = Field(default_factory=list)
    description: str
    resolution_status: Literal["unresolved"] = "unresolved"


class CategoryScore(BaseModel):
    category: str
    weight: float
    bullish_contribution: float = Field(ge=0.0, le=100.0)
    bearish_contribution: float = Field(ge=0.0, le=100.0)
    bullish_unit: float = Field(ge=0.0, le=1.0)
    bearish_unit: float = Field(ge=0.0, le=1.0)
    bullish_evidence_ids: list[str] = Field(default_factory=list)
    bearish_evidence_ids: list[str] = Field(default_factory=list)


class ConfluenceDataQuality(BaseModel):
    overall: str
    is_analysis_complete: bool
    timeframes_used: list[Timeframe] = Field(default_factory=list)
    timeframes_unavailable: list[Timeframe] = Field(default_factory=list)
    timeframes_stale: list[Timeframe] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ConfluenceResult(BaseModel):
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    calculated_at: datetime
    config_version: str
    bullish_score: float = Field(ge=0.0, le=100.0)
    bearish_score: float = Field(ge=0.0, le=100.0)
    category_scores: list[CategoryScore] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    excluded_evidence: list[EvidenceItem] = Field(default_factory=list)
    conflicts: list[ConflictItem] = Field(default_factory=list)
    preliminary_assessment: PreliminaryAssessment
    assessment_strength: Literal["strong", "moderate", "none"] = "none"
    data_quality: ConfluenceDataQuality
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)
