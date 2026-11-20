"""API schemas for AI orchestration (Phase 5.4)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.ai.explainer.schemas import AnalysisExplanation, VisionComparisonSummary
from app.ai.explainer.snapshot import AnalysisSnapshot
from app.ai.vision.schemas import VisionResult
from app.api.schemas.decision import DecisionResponse
from app.api.schemas.trade_plan import TradePlanResponse
from app.exchanges.types import ExchangeId, MarketType


class AiAnalyzeRequest(BaseModel):
    exchange: ExchangeId
    market_type: MarketType
    symbol: str
    timeframe: str | None = None
    account_balance: float | None = Field(default=None, gt=0)
    risk_percent: float | None = Field(default=None, gt=0, le=5)
    include_explanation: bool = True


class AiAnalyzeResponse(BaseModel):
    status: str
    request_id: str
    exchange: ExchangeId
    market_type: MarketType
    symbol: str
    timeframe: str | None = None
    decision: DecisionResponse
    trade_plan: TradePlanResponse
    snapshot: AnalysisSnapshot
    explanation: AnalysisExplanation | None = None
    message: str | None = None


class AiVisionAnalyzeResponse(BaseModel):
    status: str
    request_id: str
    vision: VisionResult


class AiCompareRequest(BaseModel):
    snapshot: AnalysisSnapshot
    vision: VisionResult


class AiCompareResponse(BaseModel):
    status: str
    request_id: str
    comparison: VisionComparisonSummary
    snapshot_decision: str
    notes: list[str] = Field(default_factory=list)
