"""Phase 6.0.3 — automatic Analyze persistence (unit / mocked)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

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
from app.db.exceptions import IdempotencyConflictError, PersistenceUnavailableError
from app.db.identity import new_analysis_run_id
from app.db.repositories.analysis import AnalysisPersistResult
from app.exchanges.types import ExchangeId, MarketType
from app.services.analysis_persistence_service import (
    LivePersistOutcome,
    flatten_decision_for_persist,
    flatten_trade_plan_for_persist,
    persist_live_analyze_bundle,
)


def _decision(**overrides) -> DecisionResponse:
    payload = dict(
        exchange="binance",
        symbol="BTC/USDT",
        market_type="spot",
        decision_id="d1",
        decision="NO TRADE",
        decision_reason="unit test",
        lifecycle="blocked",
        confluence_scores=ConfluenceScoreSummary(
            bullish_score=1.0, bearish_score=2.0, preliminary_assessment=None
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
        take_profit_prices=[110.0, 120.0],
        primary_rr=2.0,
        supporting_evidence=["e1"],
        blocking_conditions=["b1"],
        conflict_ids=[],
        data_quality=DecisionDataQuality(overall="ok", is_analysis_complete=True),
        analysis_only_disclaimer="Analysis only",
        configuration_version="decision-v1",
        analysis_timestamp=datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
        data_source="test",
    )
    payload.update(overrides)
    return DecisionResponse(**payload)


def _plan(**overrides) -> TradePlanResponse:
    payload = dict(
        exchange="binance",
        symbol="BTC/USDT",
        market_type="spot",
        plan_id="plan_test_1",
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
            invalidation_explanation="t",
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
    payload.update(overrides)
    return TradePlanResponse(**payload)


def test_flatten_decision_and_plan_extracts():
    d = flatten_decision_for_persist(_decision())
    assert d["entry_reference_price"] == 100.0
    assert d["bullish_score"] == 1.0
    assert d["evidence"] == ["e1"]
    p = flatten_trade_plan_for_persist(_plan())
    assert p["stop_loss_price"] == 90.0
    assert p["take_profit_prices"] == [110.0]
    assert p["timeframe"] == "1h"


@pytest.mark.asyncio
async def test_persist_disabled_analysis_still_ok():
    with patch(
        "app.services.analysis_persistence_service.is_persistence_active",
        return_value=False,
    ):
        out = await persist_live_analyze_bundle(
            exchange=ExchangeId.BINANCE,
            market_type=MarketType.SPOT,
            symbol="BTC/USDT",
            decision=_decision(),
            trade_plan=_plan(),
            timeframe="1h",
        )
    assert out.status == "disabled"
    assert out.analysis_run_id.startswith("ar_")
    assert out.snapshot_id is None


@pytest.mark.asyncio
async def test_persist_success_saved():
    run_id = new_analysis_run_id()
    fake = AnalysisPersistResult(
        analysis_run_id=run_id,
        snapshot_id=uuid.uuid4(),
        decision_row_id=uuid.uuid4(),
        trade_plan_row_id=uuid.uuid4(),
        consistency_status="ALIGNED",
        content_hash="abc",
        created=True,
        idempotent=False,
        analysis_session_id=uuid.uuid4(),
    )
    with (
        patch(
            "app.services.analysis_persistence_service.is_persistence_active",
            return_value=True,
        ),
        patch(
            "app.services.analysis_persistence_service.persist_analysis_bundle",
            new=AsyncMock(return_value=fake),
        ) as mocked,
    ):
        out = await persist_live_analyze_bundle(
            exchange=ExchangeId.BINANCE,
            market_type=MarketType.SPOT,
            symbol="BTC/USDT",
            decision=_decision(),
            trade_plan=_plan(),
            timeframe="1h",
            analysis_run_id=run_id,
        )
    assert out.status == "saved"
    assert out.analysis_run_id == run_id
    assert out.consistency_status == "ALIGNED"
    assert mocked.await_count == 1
    assert mocked.await_args.kwargs["analysis_run_id"] == run_id
    assert mocked.await_args.kwargs["ensure_analysis_session"] is True


@pytest.mark.asyncio
async def test_persist_idempotent_retry_same_run():
    run_id = new_analysis_run_id()
    sid = uuid.uuid4()
    fake = AnalysisPersistResult(
        analysis_run_id=run_id,
        snapshot_id=sid,
        decision_row_id=uuid.uuid4(),
        trade_plan_row_id=uuid.uuid4(),
        consistency_status="ALIGNED",
        content_hash="abc",
        created=False,
        idempotent=True,
        analysis_session_id=uuid.uuid4(),
    )
    with (
        patch(
            "app.services.analysis_persistence_service.is_persistence_active",
            return_value=True,
        ),
        patch(
            "app.services.analysis_persistence_service.persist_analysis_bundle",
            new=AsyncMock(return_value=fake),
        ),
    ):
        out = await persist_live_analyze_bundle(
            exchange=ExchangeId.BINANCE,
            market_type=MarketType.SPOT,
            symbol="BTC/USDT",
            decision=_decision(),
            trade_plan=_plan(),
            analysis_run_id=run_id,
        )
    assert out.status == "idempotent"
    assert out.snapshot_id == str(sid)


@pytest.mark.asyncio
async def test_persist_conflict_does_not_overwrite():
    with (
        patch(
            "app.services.analysis_persistence_service.is_persistence_active",
            return_value=True,
        ),
        patch(
            "app.services.analysis_persistence_service.persist_analysis_bundle",
            new=AsyncMock(
                side_effect=IdempotencyConflictError(
                    "mismatch",
                    identity_key="ar_x",
                    existing_hash="a",
                    incoming_hash="b",
                )
            ),
        ),
    ):
        out = await persist_live_analyze_bundle(
            exchange=ExchangeId.BINANCE,
            market_type=MarketType.SPOT,
            symbol="BTC/USDT",
            decision=_decision(),
            trade_plan=_plan(),
            analysis_run_id="ar_x",
        )
    assert out.status == "conflict"
    assert out.snapshot_id is None


@pytest.mark.asyncio
async def test_persist_db_unavailable_soft_fails():
    with (
        patch(
            "app.services.analysis_persistence_service.is_persistence_active",
            return_value=True,
        ),
        patch(
            "app.services.analysis_persistence_service.persist_analysis_bundle",
            new=AsyncMock(side_effect=PersistenceUnavailableError("down")),
        ),
    ):
        out = await persist_live_analyze_bundle(
            exchange=ExchangeId.BINANCE,
            market_type=MarketType.SPOT,
            symbol="BTC/USDT",
            decision=_decision(),
            trade_plan=_plan(),
        )
    assert out.status == "failed"
    assert "unavailable" in (out.detail or "").lower()
    assert "password" not in (out.detail or "").lower()
    assert "://" not in (out.detail or "")


@pytest.mark.asyncio
async def test_independent_runs_get_distinct_ids():
    with patch(
        "app.services.analysis_persistence_service.is_persistence_active",
        return_value=False,
    ):
        a = await persist_live_analyze_bundle(
            exchange=ExchangeId.BINANCE,
            market_type=MarketType.SPOT,
            symbol="BTC/USDT",
            decision=_decision(),
            trade_plan=_plan(),
        )
        b = await persist_live_analyze_bundle(
            exchange=ExchangeId.BINANCE,
            market_type=MarketType.SPOT,
            symbol="BTC/USDT",
            decision=_decision(),
            trade_plan=_plan(),
        )
    assert a.analysis_run_id != b.analysis_run_id


def test_analyze_route_soft_persist_and_returns_decision(monkeypatch):
    from app.ai.common import AiStatus
    from app.ai.explainer.schemas import AnalysisExplanation
    from app.ai.explainer.snapshot import AnalysisSnapshot
    from app.main import app

    decision = _decision()
    plan = _plan()
    snap = AnalysisSnapshot(
        exchange="binance",
        market_type="spot",
        symbol="BTC/USDT",
        analysis_timestamp="2024-06-01T12:00:00+00:00",
        decision="NO TRADE",
        decision_reason="t",
        lifecycle="blocked",
        data_freshness="LIVE",
    )
    explanation = AnalysisExplanation(status=AiStatus.OK.value, summary="ok")

    async def fake_analyze(**kwargs):
        return decision, plan, snap, explanation

    async def fake_persist(**kwargs):
        return LivePersistOutcome(
            status="saved",
            analysis_run_id="ar_testpersist",
            snapshot_id=str(uuid.uuid4()),
            analysis_session_id=str(uuid.uuid4()),
            consistency_status="ALIGNED",
            detail=None,
            correlation_id="ar_testpersist",
        )

    monkeypatch.setattr("app.api.routes.ai.run_ai_analyze", fake_analyze)
    monkeypatch.setattr(
        "app.api.routes.ai.persist_live_analyze_bundle", fake_persist
    )

    client = TestClient(app)
    resp = client.post(
        "/api/v1/ai/analyze",
        json={
            "exchange": "binance",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "include_explanation": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"]["decision"] == "NO TRADE"
    assert body["analysis_run_id"] == "ar_testpersist"
    assert body["persistence_status"] == "saved"
    assert "password" not in resp.text.lower()
    assert "postgresql" not in resp.text.lower()


@pytest.mark.asyncio
async def test_atomic_rollback_on_mid_write_failure():
    from app.db.repositories import analysis as repo

    session = MagicMock()
    session.scalar = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.flush = AsyncMock(side_effect=[None, RuntimeError("boom")])
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    factory = MagicMock(return_value=session)

    with (
        patch.object(repo, "is_persistence_active", return_value=True),
        patch.object(repo, "get_async_session_factory", return_value=factory),
        patch.object(
            repo,
            "get_or_create_analysis_session",
            new=AsyncMock(return_value=uuid.uuid4()),
        ),
    ):
        with pytest.raises(RuntimeError):
            await repo.persist_analysis_bundle(
                exchange="binance",
                market_type="spot",
                symbol="BTC/USDT",
                decision={
                    "decision": "NO TRADE",
                    "decision_reason": "t",
                    "analysis_timestamp": "2024-06-01T12:00:00Z",
                    "configuration_version": "v",
                },
                trade_plan={
                    "plan_id": "p1",
                    "plan_status": "blocked",
                    "analysis_timestamp": "2024-06-01T12:00:00Z",
                    "configuration_version": "v",
                    "eligibility": {},
                },
                analysis_run_id="ar_atomic_test",
            )
    session.rollback.assert_awaited()
    session.commit.assert_not_awaited()
    session.close.assert_awaited()


def test_replay_routes_do_not_import_live_persist():
    """Isolation: live persist is only wired on AI analyze routes."""
    from pathlib import Path

    replay = Path("app/api/routes/replay.py").read_text(encoding="utf-8")
    assert "persist_live_analyze_bundle" not in replay
    assert "persist_analysis_bundle" not in replay
