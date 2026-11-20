"""AI Vision + Explainer orchestration routes (Phase 5.4)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.ai.compare import compare_vision_to_snapshot
from app.ai.common import AiStatus
from app.ai.explainer.snapshot import AnalysisSnapshot
from app.ai.vision.image_validation import ImageValidationError
from app.ai.vision.schemas import VisionResult
from app.api.routes.market import _http_for_exchange_error, _normalize_symbol
from app.api.schemas.ai import (
    AiAnalyzeRequest,
    AiAnalyzeResponse,
    AiCompareRequest,
    AiCompareResponse,
    AiVisionAnalyzeResponse,
)
from app.core.config import get_settings
from app.exchanges.exceptions import ExchangeError
from app.exchanges.types import ExchangeId, MarketType
from app.services.ai_analysis_service import run_ai_analyze, run_vision_analyze

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/analyze", response_model=AiAnalyzeResponse)
async def ai_analyze(body: AiAnalyzeRequest) -> AiAnalyzeResponse:
    """Run deterministic analysis and optional AI explanation."""
    internal = _normalize_symbol(body.symbol)
    request_id = f"ai_{uuid.uuid4().hex[:12]}"
    try:
        decision, trade_plan, snapshot, explanation = await run_ai_analyze(
            exchange=body.exchange,
            market_type=body.market_type,
            symbol=internal,
            account_balance=body.account_balance,
            risk_percent=body.risk_percent,
        )
    except ExchangeError as exc:
        raise _http_for_exchange_error(exc) from exc

    if not body.include_explanation:
        explanation = None

    status = explanation.status if explanation else AiStatus.OK.value
    return AiAnalyzeResponse(
        status=status,
        request_id=request_id,
        exchange=body.exchange,
        market_type=body.market_type,
        symbol=decision.symbol,
        timeframe=body.timeframe,
        decision=decision,
        trade_plan=trade_plan,
        snapshot=snapshot,
        explanation=explanation,
        message=explanation.message if explanation else None,
    )


@router.post("/vision/analyze", response_model=AiVisionAnalyzeResponse)
async def ai_vision_analyze(
    file: UploadFile = File(...),
) -> AiVisionAnalyzeResponse:
    """Observe an uploaded chart screenshot (observational only)."""
    settings = get_settings()
    request_id = f"vis_{uuid.uuid4().hex[:12]}"
    max_bytes = int(settings.max_upload_size_mb * 1024 * 1024)

    raw = await file.read()
    if len(raw) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Image exceeds maximum size of {settings.max_upload_size_mb} MB.",
        )

    try:
        vision = await run_vision_analyze(raw)
    except ImageValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    return AiVisionAnalyzeResponse(
        status=vision.status,
        request_id=request_id,
        vision=vision,
    )


@router.post("/compare", response_model=AiCompareResponse)
async def ai_compare(body: AiCompareRequest) -> AiCompareResponse:
    """Compare validated vision observations with a deterministic snapshot."""
    request_id = f"cmp_{uuid.uuid4().hex[:12]}"
    comparison = compare_vision_to_snapshot(body.vision, body.snapshot)
    return AiCompareResponse(
        status=comparison.status,
        request_id=request_id,
        comparison=comparison,
        snapshot_decision=body.snapshot.decision,
        notes=list(comparison.notes),
    )


@router.post("/analyze-with-vision", response_model=AiAnalyzeResponse)
async def ai_analyze_with_vision(
    exchange: ExchangeId = Form(...),
    market_type: MarketType = Form(...),
    symbol: str = Form(...),
    timeframe: str | None = Form(default=None),
    account_balance: float | None = Form(default=None),
    risk_percent: float | None = Form(default=None),
    file: UploadFile | None = File(default=None),
) -> AiAnalyzeResponse:
    """Optional convenience: deterministic analyze + vision + explanation."""
    request_id = f"aiv_{uuid.uuid4().hex[:12]}"
    internal = _normalize_symbol(symbol)
    vision: VisionResult | None = None
    if file is not None and file.filename:
        raw = await file.read()
        try:
            vision = await run_vision_analyze(raw)
        except ImageValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": exc.code, "message": exc.message},
            ) from exc

    try:
        decision, trade_plan, snapshot, explanation = await run_ai_analyze(
            exchange=exchange,
            market_type=market_type,
            symbol=internal,
            account_balance=account_balance,
            risk_percent=risk_percent,
            vision=vision,
        )
    except ExchangeError as exc:
        raise _http_for_exchange_error(exc) from exc

    return AiAnalyzeResponse(
        status=explanation.status,
        request_id=request_id,
        exchange=exchange,
        market_type=market_type,
        symbol=decision.symbol,
        timeframe=timeframe,
        decision=decision,
        trade_plan=trade_plan,
        snapshot=snapshot,
        explanation=explanation,
        message=explanation.message,
    )
