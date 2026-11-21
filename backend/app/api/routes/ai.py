"""AI Vision + Explainer orchestration routes (Phase 5.4 / 5.4.2.2)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.ai.compare import compare_vision_to_snapshot
from app.ai.common import AiStatus
from app.ai.explainer.snapshot import AnalysisSnapshot
from app.ai.vision.image_validation import ImageValidationError
from app.ai.vision.recognition import (
    price_discrepancy_pct,
    recognition_summary,
)
from app.ai.vision.schemas import VisionResult
from app.api.routes.market import _http_for_exchange_error, _normalize_symbol
from app.api.schemas.ai import (
    AiAnalyzeRequest,
    AiAnalyzeResponse,
    AiCompareRequest,
    AiCompareResponse,
    AiVisionAnalyzeResponse,
    PriceComparisonSummary,
    ScreenshotRecognitionSummary,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.exchanges.exceptions import ExchangeError
from app.exchanges.manager import get_exchange_manager
from app.exchanges.types import ExchangeId, MarketType
from app.services.ai_analysis_service import run_ai_analyze, run_vision_analyze
from app.services.analysis_persistence_service import persist_live_analyze_bundle

router = APIRouter(prefix="/ai", tags=["ai"])
logger = get_logger(__name__)

_VALID_ANALYSIS_MODES = frozenset({"LIVE_MARKET", "UPLOADED_IMAGE"})


def _normalize_analysis_mode(raw: str | None) -> str:
    mode = (raw or "LIVE_MARKET").strip().upper()
    if mode not in _VALID_ANALYSIS_MODES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_ANALYSIS_MODE",
                "message": "analysis_mode must be LIVE_MARKET or UPLOADED_IMAGE.",
            },
        )
    return mode


def _session_source_for_mode(mode: str) -> str:
    return "uploaded_image" if mode == "UPLOADED_IMAGE" else "live_market"


def _orchestration_vision_status(
    vision: VisionResult,
) -> tuple[str, str | None]:
    """Map VisionResult.status → analyze-with-vision orchestration fields.

    Only AiStatus.OK is reported as vision_status=\"ok\". Provider/auth/timeout/
    rate-limit/invalid-response failures remain soft-fail \"unavailable\".
    """
    status = getattr(vision, "status", None)
    if status == AiStatus.OK.value:
        return "ok", None
    detail = getattr(vision, "message", None) or (
        "Vision analysis failed; deterministic analysis preserved."
    )
    if status == AiStatus.AI_UNAVAILABLE.value:
        return (
            "unavailable",
            detail
            if detail
            else "Vision model unavailable; deterministic analysis preserved.",
        )
    if status == AiStatus.TIMEOUT.value:
        return "unavailable", detail or "Vision request timed out; deterministic analysis preserved."
    if status == AiStatus.RATE_LIMITED.value:
        return (
            "unavailable",
            detail or "Vision provider rate limit reached; deterministic analysis preserved.",
        )
    if status == AiStatus.INVALID_MODEL_RESPONSE.value:
        return (
            "unavailable",
            detail or "Vision response invalid; deterministic analysis preserved.",
        )
    return "unavailable", detail


def _recognition_model(vision: VisionResult | None) -> ScreenshotRecognitionSummary:
    return ScreenshotRecognitionSummary.model_validate(recognition_summary(vision))


async def _verified_ticker_price(
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
) -> tuple[float | None, str | None, str | None]:
    """Best-effort verified last price. Soft-fails without blocking Analyze."""
    try:
        manager = get_exchange_manager()
        ticker = await manager.fetch_ticker(exchange, symbol, market_type)
        last = getattr(ticker, "last", None)
        price = float(last) if last is not None else None
        ts = getattr(ticker, "updated_at", None)
        ts_str = None
        if isinstance(ts, datetime):
            ts_str = ts.astimezone(timezone.utc).isoformat()
        elif ts is not None:
            ts_str = str(ts)
        source = f"{exchange.value}:{market_type.value}"
        return price, ts_str, source
    except Exception as exc:  # noqa: BLE001
        logger.info("Verified ticker unavailable for price comparison: %s", type(exc).__name__)
        return None, None, None


def _price_comparison(
    vision: VisionResult | None,
    verified: float | None,
    verified_ts: str | None,
    verified_source: str | None,
) -> PriceComparisonSummary | None:
    observed = vision.observed_last_price if vision is not None else None
    if observed is None and verified is None:
        return None
    return PriceComparisonSummary(
        screenshot_observed_price=observed,
        verified_last_price=verified,
        verified_price_timestamp=verified_ts,
        verified_price_source=verified_source,
        discrepancy_pct=price_discrepancy_pct(observed, verified),
    )


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

    persist = await persist_live_analyze_bundle(
        exchange=body.exchange,
        market_type=body.market_type,
        symbol=decision.symbol,
        decision=decision,
        trade_plan=trade_plan,
        timeframe=body.timeframe,
        data_freshness=snapshot.data_freshness,
        session_source="live_market",
        snapshot_kind="live_decision_bundle",
    )

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
        analysis_mode="LIVE_MARKET",
        analysis_run_id=persist.analysis_run_id,
        persistence_status=persist.status,
        persistence_detail=persist.detail,
        consistency_status=persist.consistency_status,
        persisted_snapshot_id=persist.snapshot_id,
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
        recognition=_recognition_model(vision),
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
    analysis_mode: str | None = Form(default="LIVE_MARKET"),
    file: UploadFile | None = File(default=None),
) -> AiAnalyzeResponse:
    """Deterministic analyze + optional vision. Vision failures never block engines."""
    request_id = f"aiv_{uuid.uuid4().hex[:12]}"
    mode = _normalize_analysis_mode(analysis_mode)
    internal = _normalize_symbol(symbol)
    vision: VisionResult | None = None
    vision_status = "skipped"
    vision_detail: str | None = None

    if mode == "UPLOADED_IMAGE" and (file is None):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "UPLOAD_REQUIRED",
                "message": "UPLOADED_IMAGE mode requires a chart image file.",
            },
        )

    if file is not None:
        raw = await file.read()
        if raw:
            try:
                vision = await run_vision_analyze(raw)
                vision_status, vision_detail = _orchestration_vision_status(vision)
            except ImageValidationError as exc:
                # Soft-fail: keep deterministic Analyze intact when symbol/TF known.
                vision = None
                vision_status = "invalid_image"
                vision_detail = exc.message
            except Exception:  # noqa: BLE001
                vision = None
                vision_status = "unavailable"
                vision_detail = "Vision analysis failed; deterministic analysis preserved."

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

    verified_price, verified_ts, verified_source = await _verified_ticker_price(
        exchange, market_type, decision.symbol
    )
    comparison = _price_comparison(vision, verified_price, verified_ts, verified_source)

    # One Analyze orchestration → one persistence attempt (vision is observational).
    persist = await persist_live_analyze_bundle(
        exchange=exchange,
        market_type=market_type,
        symbol=decision.symbol,
        decision=decision,
        trade_plan=trade_plan,
        timeframe=timeframe,
        data_freshness=snapshot.data_freshness,
        session_source=_session_source_for_mode(mode),
        snapshot_kind=(
            "uploaded_image_decision_bundle"
            if mode == "UPLOADED_IMAGE"
            else "live_decision_bundle"
        ),
    )

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
        vision=vision,
        vision_status=vision_status,
        vision_detail=vision_detail,
        analysis_mode=mode,
        recognition=_recognition_model(vision) if vision is not None else None,
        price_comparison=comparison,
        analysis_run_id=persist.analysis_run_id,
        persistence_status=persist.status,
        persistence_detail=persist.detail,
        consistency_status=persist.consistency_status,
        persisted_snapshot_id=persist.snapshot_id,
    )
