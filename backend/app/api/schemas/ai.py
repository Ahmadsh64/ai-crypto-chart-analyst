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


class ScreenshotRecognitionSummary(BaseModel):
    """OCR/visual estimates from an uploaded chart — never verified market data."""

    detected_symbol: str | None = None
    symbol_confidence: float | None = None
    detected_timeframe: str | None = None
    timeframe_confidence: float | None = None
    detected_exchange: str | None = None
    detected_platform: str | None = None
    observed_last_price: float | None = None
    observed_price_confidence: float | None = None
    observed_price_label: str | None = None
    needs_symbol_confirmation: bool = True
    needs_timeframe_confirmation: bool = True
    disclaimer: str


class PriceComparisonSummary(BaseModel):
    screenshot_observed_price: float | None = None
    verified_last_price: float | None = None
    verified_price_timestamp: str | None = None
    verified_price_source: str | None = None
    discrepancy_pct: float | None = None
    note: str = (
        "Screenshot-observed price is OCR/visual only. "
        "Verified price comes from the selected exchange adapter."
    )


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
    # Phase 5.4.2 — optional vision payload from analyze-with-vision (observational).
    vision: VisionResult | None = None
    vision_status: str | None = Field(
        default=None,
        description="ok | skipped | unavailable | invalid_image",
    )
    vision_detail: str | None = None
    # Phase 5.4.2.2 — analysis mode + recognition / price comparison (observational).
    analysis_mode: str | None = Field(
        default=None,
        description="LIVE_MARKET | UPLOADED_IMAGE",
    )
    recognition: ScreenshotRecognitionSummary | None = None
    price_comparison: PriceComparisonSummary | None = None
    # Phase 6.0.3 — soft persistence metadata (never blocks Analyze)
    analysis_run_id: str | None = None
    persistence_status: str | None = Field(
        default=None,
        description="disabled | saved | idempotent | failed | conflict",
    )
    persistence_detail: str | None = None
    consistency_status: str | None = None
    persisted_snapshot_id: str | None = None


class AiVisionAnalyzeResponse(BaseModel):
    status: str
    request_id: str
    vision: VisionResult
    recognition: ScreenshotRecognitionSummary | None = None


class AiCompareRequest(BaseModel):
    snapshot: AnalysisSnapshot
    vision: VisionResult


class AiCompareResponse(BaseModel):
    status: str
    request_id: str
    comparison: VisionComparisonSummary
    snapshot_decision: str
    notes: list[str] = Field(default_factory=list)
