"""Orchestrate deterministic analysis + AI explanation (Phase 5.4)."""

from __future__ import annotations

from app.ai.compare import compare_vision_to_snapshot
from app.ai.explainer.schemas import AnalysisExplanation
from app.ai.explainer.service import explain_analysis
from app.ai.explainer.snapshot import AnalysisSnapshot, build_analysis_snapshot
from app.ai.vision.schemas import VisionResult
from app.ai.vision.service import analyze_chart_image
from app.api.schemas.decision import DecisionResponse
from app.api.schemas.trade_plan import TradePlanResponse
from app.exchanges.types import ExchangeId, MarketType
from app.services.decision_service import compute_decision_response
from app.services.trade_plan_service import compute_trade_plan_response


async def run_deterministic_analyze(
    *,
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    account_balance: float | None = None,
    risk_percent: float | None = None,
) -> tuple[DecisionResponse, TradePlanResponse, AnalysisSnapshot]:
    # Decision already builds shared analysis context + trade plan internally,
    # but we also fetch trade plan response for the full plan payload.
    decision = await compute_decision_response(
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        account_balance=account_balance,
        risk_percent=risk_percent,
    )
    trade_plan = await compute_trade_plan_response(
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        account_balance=account_balance,
        risk_percent=risk_percent,
    )
    freshness = "LIVE" if decision.data_quality and decision.data_quality.is_analysis_complete else "PARTIAL"
    snapshot = build_analysis_snapshot(decision, trade_plan, data_freshness=freshness)
    return decision, trade_plan, snapshot


async def run_ai_analyze(
    *,
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    account_balance: float | None = None,
    risk_percent: float | None = None,
    vision: VisionResult | None = None,
) -> tuple[DecisionResponse, TradePlanResponse, AnalysisSnapshot, AnalysisExplanation]:
    decision, trade_plan, snapshot = await run_deterministic_analyze(
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        account_balance=account_balance,
        risk_percent=risk_percent,
    )
    comparison = compare_vision_to_snapshot(vision, snapshot) if vision else None
    explanation = await explain_analysis(
        snapshot,
        vision=vision,
        vision_comparison=comparison,
    )
    return decision, trade_plan, snapshot, explanation


async def run_vision_analyze(image_bytes: bytes) -> VisionResult:
    return await analyze_chart_image(image_bytes)
