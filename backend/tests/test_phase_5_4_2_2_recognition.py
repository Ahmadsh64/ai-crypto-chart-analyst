"""Phase 5.4.2.2 — screenshot recognition helpers and upload-mode Analyze wiring."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.ai.common import AiStatus
from app.ai.explainer.schemas import AnalysisExplanation
from app.ai.explainer.snapshot import AnalysisSnapshot
from app.ai.vision.recognition import (
    needs_symbol_confirmation,
    needs_timeframe_confirmation,
    parse_observed_price,
    price_discrepancy_pct,
    recognition_summary,
)
from app.ai.vision.schemas import VisionResult
from app.analysis.decision_engine.models import (
    ConfluenceScoreSummary,
    DecisionDataQuality,
    EntryConfirmationResult,
)
from app.analysis.trade_plan.models import (
    EligibilityResult,
    EntryZone,
    StopLossPlan,
    TakeProfitTarget,
    TradePlanDataQuality,
    ValidationResult,
)
from app.api.schemas.decision import DecisionResponse
from app.api.schemas.trade_plan import TradePlanResponse
from app.main import create_app
from app.services.analysis_persistence_service import LivePersistOutcome


def test_parse_observed_price_variants():
    assert parse_observed_price(61234.5) == 61234.5
    assert parse_observed_price("61,234.50") == 61234.5
    assert parse_observed_price("$1,234.56") == 1234.56
    assert parse_observed_price("not-a-price") is None
    assert parse_observed_price(None) is None


def test_needs_confirmation_thresholds():
    low = VisionResult(
        status=AiStatus.OK.value,
        detected_symbol="BTC/USDT",
        symbol_confidence=0.4,
        detected_timeframe="1h",
        timeframe_confidence=0.4,
    )
    assert needs_symbol_confirmation(low) is True
    assert needs_timeframe_confirmation(low) is True

    high = VisionResult(
        status=AiStatus.OK.value,
        detected_symbol="ETH/USDT",
        symbol_confidence=0.95,
        detected_timeframe="15m",
        timeframe_confidence=0.9,
    )
    assert needs_symbol_confirmation(high) is False
    assert needs_timeframe_confirmation(high) is False

    missing = VisionResult(status=AiStatus.OK.value)
    assert needs_symbol_confirmation(missing) is True
    assert needs_timeframe_confirmation(None) is True


def test_price_discrepancy_and_summary():
    assert price_discrepancy_pct(110.0, 100.0) == pytest.approx(10.0)
    assert price_discrepancy_pct(None, 100.0) is None
    vision = VisionResult(
        status=AiStatus.OK.value,
        detected_symbol="BTC/USDT",
        symbol_confidence=0.8,
        detected_timeframe="1h",
        timeframe_confidence=0.85,
        observed_last_price=100.0,
    )
    summary = recognition_summary(vision)
    assert summary["needs_symbol_confirmation"] is False
    assert summary["observed_last_price"] == 100.0
    assert "OCR" in summary["disclaimer"] or "screenshot" in summary["disclaimer"].lower()


def _decision() -> DecisionResponse:
    return DecisionResponse(
        exchange="binance",
        symbol="BTC/USDT",
        market_type="spot",
        decision_id="d1",
        decision="WAIT",
        decision_reason="unit",
        lifecycle="awaiting_confirmation",
        confluence_scores=ConfluenceScoreSummary(
            bullish_score=1.0, bearish_score=1.0, preliminary_assessment=None
        ),
        entry_confirmation=EntryConfirmationResult(
            status="unavailable", is_confirmed=False, explanation="n/a"
        ),
        entry_zone_summary={
            "entry_reference_price": 100.0,
            "entry_low": 99.0,
            "entry_high": 101.0,
        },
        stop_loss_price=90.0,
        take_profit_prices=[110.0],
        primary_rr=2.0,
        supporting_evidence=["HH"],
        blocking_conditions=[],
        conflict_ids=[],
        data_quality=DecisionDataQuality(overall="ok", is_analysis_complete=True),
        analysis_only_disclaimer="Analysis only",
        configuration_version="decision-v1",
        analysis_timestamp=datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
        data_source="test",
    )


def _plan() -> TradePlanResponse:
    return TradePlanResponse(
        exchange="binance",
        symbol="BTC/USDT",
        market_type="spot",
        plan_id="p1",
        plan_status="blocked",
        entry=EntryZone(
            entry_low=99.0,
            entry_high=101.0,
            entry_reference_price=100.0,
            entry_type="order_block",
            entry_source="test",
            source_event_key="k",
            timeframe="1h",
            entry_explanation="t",
        ),
        stop_loss=StopLossPlan(
            stop_loss_price=90.0,
            stop_loss_source="t",
            stop_loss_distance=10.0,
            stop_loss_distance_pct=10.0,
            buffer_value=0.0,
            invalidation_explanation="invalidated below SL",
        ),
        take_profit_targets=[
            TakeProfitTarget(
                index=1,
                label="TP1",
                price=110.0,
                source="t",
                distance=10.0,
                distance_pct=10.0,
                risk_reward_ratio=1.0,
                explanation="t",
            )
        ],
        validation=ValidationResult(is_valid=False),
        eligibility=EligibilityResult(is_eligible=False, blocking_reasons=["blocked"]),
        configuration_version="plan-v1",
        analysis_timestamp=datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
        data_quality=TradePlanDataQuality(overall="ok", is_analysis_complete=True),
        analysis_only_disclaimer="Analysis only",
        data_source="test",
    )


def _snapshot(decision: DecisionResponse) -> AnalysisSnapshot:
    return AnalysisSnapshot(
        exchange=str(decision.exchange),
        symbol=decision.symbol,
        market_type=str(decision.market_type),
        analysis_timestamp=decision.analysis_timestamp.isoformat(),
        data_freshness="LIVE",
        decision=decision.decision,
        decision_reason=decision.decision_reason,
        confluence_bullish=1.0,
        confluence_bearish=1.0,
        conflicts=[],
        supporting_evidence=list(decision.supporting_evidence),
        blocking_conditions=[],
        entry_reference_price=100.0,
        entry_low=99.0,
        entry_high=101.0,
        stop_loss_price=90.0,
        take_profit_prices=[110.0],
        primary_rr=2.0,
        analysis_only_disclaimer="Analysis only",
    )


def _explanation() -> AnalysisExplanation:
    return AnalysisExplanation(
        status=AiStatus.OK.value,
        summary="ok",
        decision_explanation="wait",
    )


def _png_bytes() -> bytes:
    # Minimal valid 1x1 PNG
    import base64

    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


def test_uploaded_image_mode_requires_file():
    app = create_app()
    client = TestClient(app)
    resp = client.post(
        "/api/v1/ai/analyze-with-vision",
        data={
            "exchange": "binance",
            "market_type": "spot",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "analysis_mode": "UPLOADED_IMAGE",
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "UPLOAD_REQUIRED"


def test_uploaded_image_mode_persists_with_session_source():
    app = create_app()
    client = TestClient(app)
    vision = VisionResult(
        status=AiStatus.OK.value,
        detected_symbol="BTC/USDT",
        symbol_confidence=0.9,
        detected_timeframe="1h",
        timeframe_confidence=0.9,
        observed_last_price=101.0,
        observations=[],
    )
    decision = _decision()
    persist = LivePersistOutcome(
        status="saved",
        analysis_run_id="ar_upload_test",
        snapshot_id="snap1",
        analysis_session_id="sess1",
        consistency_status="ALIGNED",
        detail=None,
        correlation_id="ar_upload_test",
    )
    snap = _snapshot(decision)
    explanation = _explanation()

    with (
        patch(
            "app.api.routes.ai.run_vision_analyze",
            new=AsyncMock(return_value=vision),
        ),
        patch(
            "app.api.routes.ai.run_ai_analyze",
            new=AsyncMock(return_value=(decision, _plan(), snap, explanation)),
        ),
        patch(
            "app.api.routes.ai.persist_live_analyze_bundle",
            new=AsyncMock(return_value=persist),
        ) as persist_mock,
        patch(
            "app.api.routes.ai._verified_ticker_price",
            new=AsyncMock(return_value=(100.0, "2024-06-01T12:00:00+00:00", "binance:spot")),
        ),
    ):
        resp = client.post(
            "/api/v1/ai/analyze-with-vision",
            data={
                "exchange": "binance",
                "market_type": "spot",
                "symbol": "BTC/USDT",
                "timeframe": "1h",
                "analysis_mode": "UPLOADED_IMAGE",
            },
            files={"file": ("chart.png", _png_bytes(), "image/png")},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["analysis_mode"] == "UPLOADED_IMAGE"
    assert body["analysis_run_id"] == "ar_upload_test"
    assert body["recognition"]["detected_symbol"] == "BTC/USDT"
    assert body["price_comparison"]["discrepancy_pct"] == pytest.approx(1.0)
    kwargs = persist_mock.await_args.kwargs
    assert kwargs["session_source"] == "uploaded_image"
    assert kwargs["snapshot_kind"] == "uploaded_image_decision_bundle"
