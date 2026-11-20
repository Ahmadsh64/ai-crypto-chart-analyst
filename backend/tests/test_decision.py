"""Phase 4.4 — Final decision engine tests."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.analysis.confluence.config import DEFAULT_CONFLUENCE_CONFIG
from app.analysis.confluence.models import (
    ConflictItem,
    ConflictSeverity,
    ConfluenceDataQuality,
    ConfluenceResult,
    EvidenceDirection,
    EvidenceItem,
    EvidenceType,
    PreliminaryAssessment,
)
from app.analysis.decision_engine.config import DEFAULT_DECISION_CONFIG
from app.analysis.decision_engine.decision_rules import resolve_decision
from app.analysis.decision_engine.entry_confirmation import evaluate_entry_confirmation
from app.analysis.decision_engine.models import EntryConfirmationResult
from app.analysis.multi_timeframe.models import (
    MultiTimeframeSnapshot,
    SyncMetadata,
    TimeframeSeriesSummary,
)
from app.analysis.trade_plan.models import (
    EligibilityResult,
    EntryZone,
    PositionSizing,
    RiskMetrics,
    StopLossPlan,
    TakeProfitTarget,
    TradePlanDataQuality,
    TradePlanResult,
    ValidationResult,
)
from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.main import app

NOW = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)


def _ready(tf: Timeframe, price: float = 100.0) -> TimeframeSeriesSummary:
    return TimeframeSeriesSummary(
        timeframe=tf,
        purpose="x",
        duration_minutes=60,
        latest_closed_candle_time=NOW,
        latest_price=price,
        candles_count=100,
        closed_candles_count=99,
        is_ready=True,
        is_stale=False,
        data_quality="ok",
        last_updated=NOW,
    )


def _mtf(price: float = 100.0) -> MultiTimeframeSnapshot:
    tfs = [_ready(tf, price) for tf in (Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5)]
    return MultiTimeframeSnapshot(
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        calculated_at=NOW,
        config_version="mtf-v1.0.0-orchestration",
        overall_status="ready",
        ready_timeframes=[Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5],
        unavailable_timeframes=[],
        timeframes=tfs,
        sync=SyncMetadata(as_of=NOW, aligned=True),
    )


def _confluence(
    *,
    assessment: PreliminaryAssessment = PreliminaryAssessment.BULLISH_CONFLUENCE,
    strength: str = "strong",
    bull: float = 75.0,
    bear: float = 30.0,
    conflicts: list | None = None,
) -> ConfluenceResult:
    side = "bullish" if assessment == PreliminaryAssessment.BULLISH_CONFLUENCE else "bearish"
    return ConfluenceResult(
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        calculated_at=NOW,
        config_version=DEFAULT_CONFLUENCE_CONFIG.config_version,
        bullish_score=bull,
        bearish_score=bear,
        evidence=[
            EvidenceItem(
                evidence_id="e1",
                evidence_type=EvidenceType.MSS,
                category="market_structure",
                timeframe=Timeframe.H1,
                direction=EvidenceDirection(side),
                strength=1.0,
                confidence=1.0,
                source_event_key="mss1",
                source_timestamp=NOW,
                is_confirmed=True,
                is_active=True,
                explanation="x",
            )
        ],
        conflicts=conflicts or [],
        preliminary_assessment=assessment,
        assessment_strength=strength,  # type: ignore[arg-type]
        data_quality=ConfluenceDataQuality(
            overall="ready",
            is_analysis_complete=True,
            timeframes_used=[Timeframe.H4, Timeframe.H1],
        ),
        summary="t",
    )


def _plan(
    *,
    status: str = "eligible",
    direction: str = "bullish",
    price_inside: bool = True,
) -> TradePlanResult:
    entry = EntryZone(
        entry_low=98,
        entry_high=102,
        entry_reference_price=100,
        entry_type="order_block",
        entry_source="ob",
        source_event_key="ob1",
        timeframe="15m",
        entry_explanation="e",
        price_inside_zone=price_inside,
    )
    return TradePlanResult(
        plan_id="tp1",
        symbol="BTC/USDT",
        exchange=ExchangeId.BINANCE,
        market_type=MarketType.SPOT,
        direction=direction,  # type: ignore[arg-type]
        plan_status=status,  # type: ignore[arg-type]
        entry=entry if status == "eligible" else None,
        stop_loss=StopLossPlan(
            stop_loss_price=90 if direction == "bullish" else 110,
            stop_loss_source="zone",
            stop_loss_distance=10,
            stop_loss_distance_pct=10,
            buffer_value=0.5,
            invalidation_explanation="x",
        )
        if status == "eligible"
        else None,
        take_profit_targets=[
            TakeProfitTarget(
                index=1,
                label="TP1",
                price=120 if direction == "bullish" else 80,
                source="swing",
                distance=20,
                distance_pct=20,
                risk_reward_ratio=2.0,
                explanation="t",
            )
        ]
        if status == "eligible"
        else [],
        risk=RiskMetrics(
            risk_distance=10,
            risk_distance_pct=10,
            primary_rr=2.0,
            minimum_required_rr=2.0,
            meets_minimum_rr=True,
        )
        if status == "eligible"
        else None,
        position_sizing=PositionSizing(
            account_balance=10000,
            risk_percent=1,
            risk_amount=100,
            position_size=10,
            position_notional=1000,
            estimated_loss_at_sl=100,
            contract_multiplier=1,
            sizing_available=True,
            sizing_explanation="hyp",
        ),
        validation=ValidationResult(
            is_valid=status == "eligible",
            blocking_reasons=[] if status == "eligible" else ["blocked"],
        ),
        eligibility=EligibilityResult(
            is_eligible=status == "eligible",
            direction=direction,  # type: ignore[arg-type]
            blocking_reasons=[] if status == "eligible" else ["blocked"],
        ),
        configuration_version="trade-plan-v1.0.0-balanced",
        analysis_timestamp=NOW,
        data_quality=TradePlanDataQuality(
            overall="ready",
            is_analysis_complete=True,
            current_price=100,
            atr_available=True,
        ),
    )


def _confirm(ok: bool = True) -> EntryConfirmationResult:
    if ok:
        return EntryConfirmationResult(
            status="confirmed",
            is_confirmed=True,
            confirmation_type="bos",
            source_event_key="bos5m",
            timeframe="5m",
            direction="bullish",
            explanation="5M confirmed BOS",
            evidence_ids=["confirm:bos:bos5m"],
        )
    return EntryConfirmationResult(
        status="not_confirmed",
        is_confirmed=False,
        explanation="No confirmation",
        blocking_reasons=["5M entry confirmation not present."],
    )


def test_resolve_long():
    from app.analysis.decision_engine.eligibility import evaluate_decision_eligibility

    conf = _confluence()
    plan = _plan()
    el = evaluate_decision_eligibility(
        confluence=conf, trade_plan=plan, mtf_snapshot=_mtf(), config=DEFAULT_DECISION_CONFIG
    )
    assert el.is_setup_valid
    decision, life, reason, _ = resolve_decision(
        eligibility=el,
        confirmation=_confirm(True),
        trade_plan=plan,
        market_type=MarketType.USDT_M_FUTURES,
        current_price=100.0,
        price_inside_zone=True,
        setup_expired=False,
        setup_invalidated=False,
        both_directions_valid=False,
        config=DEFAULT_DECISION_CONFIG,
    )
    assert decision == "LONG"
    assert life == "entry_confirmed"
    assert "LONG" in reason


def test_resolve_wait_without_confirmation():
    from app.analysis.decision_engine.eligibility import evaluate_decision_eligibility

    conf = _confluence()
    plan = _plan()
    el = evaluate_decision_eligibility(
        confluence=conf, trade_plan=plan, mtf_snapshot=_mtf(), config=DEFAULT_DECISION_CONFIG
    )
    decision, life, reason, _ = resolve_decision(
        eligibility=el,
        confirmation=_confirm(False),
        trade_plan=plan,
        market_type=MarketType.SPOT,
        current_price=100.0,
        price_inside_zone=True,
        setup_expired=False,
        setup_invalidated=False,
        both_directions_valid=False,
        config=DEFAULT_DECISION_CONFIG,
    )
    assert decision == "WAIT"
    assert life == "awaiting_confirmation"


def test_resolve_no_trade_weak_confluence():
    from app.analysis.decision_engine.eligibility import evaluate_decision_eligibility

    conf = _confluence(assessment=PreliminaryAssessment.MIXED, strength="none", bull=40, bear=40)
    plan = _plan(status="blocked")
    el = evaluate_decision_eligibility(
        confluence=conf, trade_plan=plan, mtf_snapshot=_mtf(), config=DEFAULT_DECISION_CONFIG
    )
    decision, _, _, _ = resolve_decision(
        eligibility=el,
        confirmation=_confirm(False),
        trade_plan=plan,
        market_type=MarketType.SPOT,
        current_price=100.0,
        price_inside_zone=False,
        setup_expired=False,
        setup_invalidated=False,
        both_directions_valid=False,
        config=DEFAULT_DECISION_CONFIG,
    )
    assert decision == "NO TRADE"


def test_resolve_critical_conflict():
    from app.analysis.decision_engine.eligibility import evaluate_decision_eligibility

    conf = _confluence(
        conflicts=[
            ConflictItem(
                conflict_type="htf_structure_conflict",
                severity=ConflictSeverity.CRITICAL,
                description="4H vs 1H",
            )
        ]
    )
    plan = _plan()
    el = evaluate_decision_eligibility(
        confluence=conf, trade_plan=plan, mtf_snapshot=_mtf(), config=DEFAULT_DECISION_CONFIG
    )
    assert not el.is_setup_valid
    decision, _, _, _ = resolve_decision(
        eligibility=el,
        confirmation=_confirm(True),
        trade_plan=plan,
        market_type=MarketType.SPOT,
        current_price=100.0,
        price_inside_zone=True,
        setup_expired=False,
        setup_invalidated=False,
        both_directions_valid=False,
        config=DEFAULT_DECISION_CONFIG,
    )
    assert decision == "NO TRADE"


def test_spot_bearish_confirmed_is_not_short():
    from app.analysis.decision_engine.eligibility import evaluate_decision_eligibility

    conf = _confluence(
        assessment=PreliminaryAssessment.BEARISH_CONFLUENCE,
        bull=30,
        bear=75,
    )
    plan = _plan(direction="bearish")
    el = evaluate_decision_eligibility(
        confluence=conf, trade_plan=plan, mtf_snapshot=_mtf(), config=DEFAULT_DECISION_CONFIG
    )
    confirm = EntryConfirmationResult(
        status="confirmed",
        is_confirmed=True,
        confirmation_type="bos",
        source_event_key="bos",
        timeframe="5m",
        direction="bearish",
        explanation="5M bearish BOS",
    )
    decision, _, reason, blockers = resolve_decision(
        eligibility=el,
        confirmation=confirm,
        trade_plan=plan,
        market_type=MarketType.SPOT,
        current_price=100.0,
        price_inside_zone=True,
        setup_expired=False,
        setup_invalidated=False,
        both_directions_valid=False,
        config=DEFAULT_DECISION_CONFIG,
    )
    assert decision == "NO TRADE"
    assert "SHORT" not in decision or decision == "NO TRADE"
    assert any("Spot" in b for b in blockers) or "Spot" in reason


def test_futures_short_allowed():
    from app.analysis.decision_engine.eligibility import evaluate_decision_eligibility

    conf = _confluence(
        assessment=PreliminaryAssessment.BEARISH_CONFLUENCE,
        bull=30,
        bear=75,
    )
    plan = _plan(direction="bearish")
    # mutate market type on plan for futures
    plan = plan.model_copy(update={"market_type": MarketType.USDT_M_FUTURES})
    el = evaluate_decision_eligibility(
        confluence=conf, trade_plan=plan, mtf_snapshot=_mtf(), config=DEFAULT_DECISION_CONFIG
    )
    confirm = EntryConfirmationResult(
        status="confirmed",
        is_confirmed=True,
        confirmation_type="mss",
        source_event_key="mss",
        timeframe="5m",
        direction="bearish",
        explanation="5M MSS",
    )
    decision, life, _, _ = resolve_decision(
        eligibility=el,
        confirmation=confirm,
        trade_plan=plan,
        market_type=MarketType.USDT_M_FUTURES,
        current_price=100.0,
        price_inside_zone=True,
        setup_expired=False,
        setup_invalidated=False,
        both_directions_valid=False,
        config=DEFAULT_DECISION_CONFIG,
    )
    assert decision == "SHORT"
    assert life == "entry_confirmed"


def test_expired_setup():
    from app.analysis.decision_engine.eligibility import evaluate_decision_eligibility

    conf = _confluence()
    plan = _plan()
    el = evaluate_decision_eligibility(
        confluence=conf, trade_plan=plan, mtf_snapshot=_mtf(), config=DEFAULT_DECISION_CONFIG
    )
    decision, life, _, _ = resolve_decision(
        eligibility=el,
        confirmation=_confirm(True),
        trade_plan=plan,
        market_type=MarketType.SPOT,
        current_price=100.0,
        price_inside_zone=True,
        setup_expired=True,
        setup_invalidated=False,
        both_directions_valid=False,
        config=DEFAULT_DECISION_CONFIG,
    )
    assert decision == "NO TRADE"
    assert life == "expired"


def test_both_directions_ambiguity():
    from app.analysis.decision_engine.eligibility import evaluate_decision_eligibility

    conf = _confluence()
    plan = _plan()
    el = evaluate_decision_eligibility(
        confluence=conf, trade_plan=plan, mtf_snapshot=_mtf(), config=DEFAULT_DECISION_CONFIG
    )
    decision, _, _, _ = resolve_decision(
        eligibility=el,
        confirmation=_confirm(True),
        trade_plan=plan,
        market_type=MarketType.SPOT,
        current_price=100.0,
        price_inside_zone=True,
        setup_expired=False,
        setup_invalidated=False,
        both_directions_valid=True,
        config=DEFAULT_DECISION_CONFIG,
    )
    assert decision == "NO TRADE"


def test_entry_confirmation_empty_bundle():
    result = evaluate_entry_confirmation(
        direction="bullish",
        confirm_bundle=None,
        confirm_candles=[],
        as_of=NOW,
        config=DEFAULT_DECISION_CONFIG,
    )
    assert result.status == "unavailable"
    assert not result.is_confirmed


def test_api_decision_schema(monkeypatch):
    from app.api.schemas.decision import DecisionResponse
    from app.analysis.decision_engine.models import (
        ConfluenceScoreSummary,
        DecisionDataQuality,
        EntryConfirmationResult,
    )

    async def fake(**_k):
        return DecisionResponse(
            exchange=ExchangeId.BINANCE,
            symbol="BTC/USDT",
            market_type=MarketType.SPOT,
            decision_id="dec_test",
            decision="WAIT",
            decision_reason="WAIT: test",
            direction="bullish",
            lifecycle="awaiting_confirmation",
            confluence_scores=ConfluenceScoreSummary(
                bullish_score=75,
                bearish_score=30,
                preliminary_assessment="bullish_confluence",
                assessment_strength="strong",
            ),
            trade_plan_status="eligible",
            trade_plan_id="tp1",
            entry_confirmation=EntryConfirmationResult(
                status="not_confirmed",
                explanation="no confirm",
                blocking_reasons=["5M entry confirmation not present."],
            ),
            supporting_evidence=[],
            blocking_conditions=["5M entry confirmation not present."],
            conflict_ids=[],
            data_quality=DecisionDataQuality(
                overall="ready",
                is_analysis_complete=True,
                current_price=100,
            ),
            analysis_only_disclaimer="Analysis only — no orders are executed. Analytical conditions do not guarantee execution or profit.",
            configuration_version="decision-v1.0.0-balanced",
            analysis_timestamp=NOW,
            config={},
            data_source="binance:spot",
            metadata={"no_order_execution": True},
        )

    monkeypatch.setattr("app.api.routes.decision.compute_decision_response", fake)
    client = TestClient(app)
    res = client.get(
        "/api/v1/decision",
        params={"exchange": "binance", "market_type": "spot", "symbol": "BTC/USDT"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["decision"] == "WAIT"
    assert body["configuration_version"] == "decision-v1.0.0-balanced"


def test_config_version():
    assert DEFAULT_DECISION_CONFIG.config_version == "decision-v1.0.0-balanced"
