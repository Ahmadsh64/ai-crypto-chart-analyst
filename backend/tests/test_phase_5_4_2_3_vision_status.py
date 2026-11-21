"""Phase 5.4.2.3 — Vision orchestration status mapping (soft-fail readiness)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import uuid

import pytest
from fastapi.testclient import TestClient

from app.ai.common import AiStatus
from app.ai.explainer.schemas import AnalysisExplanation
from app.ai.explainer.snapshot import AnalysisSnapshot
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
from app.api.routes.ai import _orchestration_vision_status
from app.api.schemas.decision import DecisionResponse
from app.api.schemas.trade_plan import TradePlanResponse
from app.main import create_app
from app.services.analysis_persistence_service import LivePersistOutcome


def test_orchestration_status_ok_only_for_ok():
    mapped, detail = _orchestration_vision_status(VisionResult(status=AiStatus.OK.value))
    assert mapped == "ok"
    assert detail is None


@pytest.mark.parametrize(
    "status",
    [
        AiStatus.AI_UNAVAILABLE.value,
        AiStatus.TIMEOUT.value,
        AiStatus.RATE_LIMITED.value,
        AiStatus.INVALID_MODEL_RESPONSE.value,
        AiStatus.ERROR.value,
    ],
)
def test_orchestration_status_non_ok_is_unavailable(status: str):
    mapped, detail = _orchestration_vision_status(
        VisionResult(status=status, message="provider issue")
    )
    assert mapped == "unavailable"
    assert detail == "provider issue"


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


def _persist(run_id: str) -> LivePersistOutcome:
    return LivePersistOutcome(
        status="saved",
        analysis_run_id=run_id,
        snapshot_id=str(uuid.uuid4()),
        analysis_session_id=str(uuid.uuid4()),
        consistency_status="ALIGNED",
        detail=None,
        correlation_id=run_id,
    )


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.mark.parametrize(
    "vision_status",
    [
        AiStatus.TIMEOUT.value,
        AiStatus.RATE_LIMITED.value,
        AiStatus.ERROR.value,
        AiStatus.AI_UNAVAILABLE.value,
        AiStatus.INVALID_MODEL_RESPONSE.value,
    ],
)
def test_analyze_with_vision_marks_provider_failure_unavailable(
    client: TestClient, vision_status: str
):
    decision = _decision()
    plan = _plan()
    snapshot = _snapshot(decision)
    vision = VisionResult(
        status=vision_status,
        message="soft fail fixture",
        limitations=["unit"],
    )
    explanation = _explanation()
    persist = _persist("ar_soft")

    with (
        patch(
            "app.api.routes.ai.run_vision_analyze",
            new=AsyncMock(return_value=vision),
        ),
        patch(
            "app.api.routes.ai.run_ai_analyze",
            new=AsyncMock(return_value=(decision, plan, snapshot, explanation)),
        ) as analyze_mock,
        patch(
            "app.api.routes.ai.persist_live_analyze_bundle",
            new=AsyncMock(return_value=persist),
        ),
        patch(
            "app.api.routes.ai._verified_ticker_price",
            new=AsyncMock(
                return_value=(100.0, "2026-11-20T13:00:00+00:00", "binance")
            ),
        ),
    ):
        res = client.post(
            "/api/v1/ai/analyze-with-vision",
            data={
                "exchange": "binance",
                "market_type": "spot",
                "symbol": "BTC/USDT",
                "timeframe": "1h",
            },
            files={"file": ("chart.png", b"fakepngbytes", "image/png")},
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["vision_status"] == "unavailable"
    assert body["vision"] is not None
    assert body["decision"]["decision"] == "WAIT"
    assert analyze_mock.await_args.kwargs.get("vision") is vision
