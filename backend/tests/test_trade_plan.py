"""Phase 4.3 — Deterministic trade-plan engine tests."""

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
from app.analysis.liquidity.models import (
    LiquidityLevel,
    LiquidityResult,
    LiquiditySnapshot,
    LiquiditySourceType,
    LiquidityStatus,
    LiquidityType,
)
from app.analysis.multi_timeframe.models import (
    MultiTimeframeSnapshot,
    SyncMetadata,
    TimeframeSeriesSummary,
)
from app.analysis.ob_fvg.models import (
    ObFvgResult,
    ObFvgSnapshot,
    ObStatus,
    OrderBlock,
    StructureSourceKind,
    ZoneSide,
)
from app.analysis.trade_plan.config import DEFAULT_TRADE_PLAN_CONFIG, TradePlanConfig
from app.analysis.trade_plan.eligibility import evaluate_eligibility
from app.analysis.trade_plan.engine import analyze_trade_plan
from app.analysis.trade_plan.entry import select_entry
from app.analysis.trade_plan.models import EntryZone, StopLossPlan
from app.analysis.trade_plan.risk import calculate_position_sizing, risk_reward
from app.analysis.trade_plan.stop_loss import calculate_stop_loss
from app.analysis.trade_plan.take_profit import calculate_take_profits
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.main import app

NOW = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)


def _candle(i: int, *, close: float = 100.0) -> Candle:
    return Candle(
        timestamp=datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc).replace(
            day=1 + (i % 20), hour=i % 24
        ),
        open=close - 1,
        high=close + 2,
        low=close - 2,
        close=close,
        volume=10,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        is_closed=True,
    )


def _ready_summary(tf: Timeframe, price: float = 100.0) -> TimeframeSeriesSummary:
    return TimeframeSeriesSummary(
        timeframe=tf,
        purpose="htf_context",
        duration_minutes=60,
        latest_closed_candle_time=NOW,
        latest_price=price,
        candles_count=100,
        closed_candles_count=99,
        is_ready=True,
        is_stale=False,
        has_data_gaps=False,
        data_quality="ok",
        last_updated=NOW,
    )


def _mtf_ready(price: float = 100.0) -> MultiTimeframeSnapshot:
    tfs = [_ready_summary(tf, price) for tf in (Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5)]
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


def _evidence(direction: str = "bullish") -> EvidenceItem:
    return EvidenceItem(
        evidence_id=f"ev-{direction}",
        evidence_type=EvidenceType.MSS,
        category="market_structure",
        timeframe=Timeframe.H1,
        direction=EvidenceDirection(direction),
        strength=1.0,
        confidence=1.0,
        source_event_key=f"mss-{direction}",
        source_timestamp=NOW,
        is_confirmed=True,
        is_active=True,
        explanation=f"{direction} mss",
    )


def _confluence(
    *,
    assessment: PreliminaryAssessment = PreliminaryAssessment.BULLISH_CONFLUENCE,
    strength: str = "strong",
    bull: float = 75.0,
    bear: float = 30.0,
    conflicts: list[ConflictItem] | None = None,
    evidence: list[EvidenceItem] | None = None,
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
        category_scores=[],
        evidence=evidence or [_evidence(side)],
        excluded_evidence=[],
        conflicts=conflicts or [],
        preliminary_assessment=assessment,
        assessment_strength=strength,  # type: ignore[arg-type]
        data_quality=ConfluenceDataQuality(
            overall="ready",
            is_analysis_complete=True,
            timeframes_used=[Timeframe.H4, Timeframe.H1],
            timeframes_unavailable=[],
            timeframes_stale=[],
            limitations=[],
        ),
        summary="test",
        metadata={},
    )


def _ob(
    *,
    side: ZoneSide = ZoneSide.BULLISH,
    status: ObStatus = ObStatus.ACTIVE,
    low: float = 95.0,
    high: float = 98.0,
) -> OrderBlock:
    return OrderBlock(
        event_key=f"ob:{side.value}:test:{low}",
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.M15,
        side=side,
        status=status,
        zone_low=low,
        zone_high=high,
        boundary_method="full_range",
        source_candle_timestamp=NOW,
        source_open=low,
        source_high=high,
        source_low=low,
        source_close=(low + high) / 2,
        source_structure_kind=StructureSourceKind.BOS,
        source_structure_event_key="bos:test",
        structure_candle_timestamp=NOW,
        detection_timestamp=NOW,
        config_version="obfvg-v1.0.0-balanced",
        confirmed=True,
    )


def _ob_result(obs: list[OrderBlock] | None = None) -> ObFvgResult:
    obs = obs or [_ob()]
    bull = [o for o in obs if o.side == ZoneSide.BULLISH]
    bear = [o for o in obs if o.side == ZoneSide.BEARISH]
    return ObFvgResult(
        config={},
        snapshot=ObFvgSnapshot(
            exchange=ExchangeId.BINANCE,
            symbol="BTC/USDT",
            market_type=MarketType.SPOT,
            timeframe=Timeframe.M15,
            calculated_at=NOW,
            config_version="obfvg-v1.0.0-balanced",
            closed_candles_used=100,
            active_ob_count=len([o for o in obs if o.status == ObStatus.ACTIVE]),
            active_fvg_count=0,
            bullish_ob_count=len(bull),
            bearish_ob_count=len(bear),
            bullish_fvg_count=0,
            bearish_fvg_count=0,
        ),
        bullish_order_blocks=bull,
        bearish_order_blocks=bear,
    )


def test_eligibility_strong_bullish():
    el = evaluate_eligibility(
        _confluence(),
        _mtf_ready(),
        current_price=100.0,
        config=DEFAULT_TRADE_PLAN_CONFIG,
    )
    assert el.is_eligible
    assert el.direction == "bullish"


def test_eligibility_moderate_blocked():
    el = evaluate_eligibility(
        _confluence(strength="moderate", bull=60.0, bear=40.0),
        _mtf_ready(),
        current_price=100.0,
        config=DEFAULT_TRADE_PLAN_CONFIG,
    )
    assert not el.is_eligible
    assert any("Strong" in b for b in el.blocking_reasons)


def test_eligibility_critical_htf_conflict():
    conflict = ConflictItem(
        conflict_type="htf_structure_conflict",
        severity=ConflictSeverity.CRITICAL,
        affected_timeframes=[Timeframe.H4, Timeframe.H1],
        description="4H vs 1H",
    )
    el = evaluate_eligibility(
        _confluence(conflicts=[conflict]),
        _mtf_ready(),
        current_price=100.0,
        config=DEFAULT_TRADE_PLAN_CONFIG,
    )
    assert not el.is_eligible
    assert any("Critical" in b for b in el.blocking_reasons)


def test_eligibility_missing_price():
    el = evaluate_eligibility(
        _confluence(),
        _mtf_ready(),
        current_price=None,
        config=DEFAULT_TRADE_PLAN_CONFIG,
    )
    assert not el.is_eligible


def test_entry_valid_bullish_ob():
    entry, blockers = select_entry(
        direction="bullish",
        current_price=100.0,
        atr_value=2.0,
        setup_ob_fvg=_ob_result([_ob(low=96.0, high=98.0)]),
        setup_structure=None,
        setup_timeframe="15m",
        config=DEFAULT_TRADE_PLAN_CONFIG,
    )
    assert not blockers
    assert entry is not None
    assert entry.entry_type == "order_block"
    assert entry.entry_low == 96.0


def test_entry_rejects_invalidated_ob():
    entry, blockers = select_entry(
        direction="bullish",
        current_price=100.0,
        atr_value=2.0,
        setup_ob_fvg=_ob_result([_ob(status=ObStatus.INVALIDATED)]),
        setup_structure=None,
        setup_timeframe="15m",
        config=DEFAULT_TRADE_PLAN_CONFIG,
    )
    assert entry is None
    assert blockers


def test_entry_rejects_distant_zone():
    entry, blockers = select_entry(
        direction="bullish",
        current_price=100.0,
        atr_value=1.0,
        setup_ob_fvg=_ob_result([_ob(low=50.0, high=52.0)]),
        setup_structure=None,
        setup_timeframe="15m",
        config=DEFAULT_TRADE_PLAN_CONFIG,
    )
    assert entry is None
    assert any("ATR" in b for b in blockers)


def test_long_sl_below_entry():
    entry = EntryZone(
        entry_low=96.0,
        entry_high=98.0,
        entry_reference_price=97.0,
        entry_type="order_block",
        entry_source="bullish_order_block:active",
        source_event_key="ob:test",
        timeframe="15m",
        entry_explanation="test",
    )
    stop, _ = calculate_stop_loss(
        direction="bullish",
        entry=entry,
        atr_value=2.0,
        setup_structure=None,
        config=DEFAULT_TRADE_PLAN_CONFIG,
    )
    assert stop is not None
    assert stop.stop_loss_price < entry.entry_reference_price
    assert stop.stop_loss_distance > 0


def test_short_sl_above_entry():
    entry = EntryZone(
        entry_low=102.0,
        entry_high=104.0,
        entry_reference_price=103.0,
        entry_type="order_block",
        entry_source="bearish_order_block:active",
        source_event_key="ob:bear",
        timeframe="15m",
        entry_explanation="test",
    )
    stop, _ = calculate_stop_loss(
        direction="bearish",
        entry=entry,
        atr_value=2.0,
        setup_structure=None,
        config=DEFAULT_TRADE_PLAN_CONFIG,
    )
    assert stop is not None
    assert stop.stop_loss_price > entry.entry_reference_price


def test_rr_long_and_short():
    assert abs(risk_reward(direction="bullish", entry_price=100, stop_price=90, target_price=120) - 2.0) < 1e-9
    assert abs(risk_reward(direction="bearish", entry_price=100, stop_price=110, target_price=80) - 2.0) < 1e-9


def test_minimum_rr_rejection():
    entry = EntryZone(
        entry_low=96,
        entry_high=98,
        entry_reference_price=97,
        entry_type="order_block",
        entry_source="x",
        source_event_key="k",
        timeframe="15m",
        entry_explanation="e",
    )
    stop = StopLossPlan(
        stop_loss_price=95.5,
        stop_loss_source="zone",
        stop_loss_distance=1.5,
        stop_loss_distance_pct=1.5,
        atr_value=2.0,
        buffer_value=0.5,
        invalidation_explanation="x",
    )
    near = LiquidityLevel(
        event_key="bsl-near",
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        liquidity_type=LiquidityType.BSL,
        source_type=LiquiditySourceType.SWING,
        price=98.0,
        status=LiquidityStatus.ACTIVE,
        source_swing_keys=[],
        source_swings=[],
        detection_timestamp=NOW,
        latest_confirmation_timestamp=NOW,
        config_version="liq-v1.1.0-balanced",
    )
    liq = LiquidityResult(
        config={},
        snapshot=LiquiditySnapshot(
            exchange=ExchangeId.BINANCE,
            symbol="BTC/USDT",
            market_type=MarketType.SPOT,
            timeframe=Timeframe.H1,
            calculated_at=NOW,
            config_version="liq-v1.1.0-balanced",
            closed_candles_used=100,
            active_bsl_count=1,
            active_ssl_count=0,
            eqh_count=0,
            eql_count=0,
            sweep_count=0,
        ),
        bsl_levels=[near],
        ssl_levels=[],
    )
    targets, blockers = calculate_take_profits(
        direction="bullish",
        entry=entry,
        stop=stop,
        liquidity_results=[liq],
        structure_results=[],
        opposing_ob_fvg=None,
        config=DEFAULT_TRADE_PLAN_CONFIG,
    )
    assert targets == []
    assert blockers


def test_position_sizing_one_percent():
    entry = EntryZone(
        entry_low=96,
        entry_high=98,
        entry_reference_price=100,
        entry_type="order_block",
        entry_source="x",
        source_event_key="k",
        timeframe="15m",
        entry_explanation="e",
    )
    stop = StopLossPlan(
        stop_loss_price=90,
        stop_loss_source="zone",
        stop_loss_distance=10,
        stop_loss_distance_pct=10,
        atr_value=2.0,
        buffer_value=0.5,
        invalidation_explanation="x",
    )
    sizing = calculate_position_sizing(
        entry=entry,
        stop=stop,
        account_balance=10_000,
        risk_percent=1.0,
        market_type=MarketType.SPOT,
        config=DEFAULT_TRADE_PLAN_CONFIG,
    )
    assert sizing.sizing_available
    assert sizing.risk_amount == 100.0
    assert abs((sizing.position_size or 0) - 10.0) < 1e-9


def test_invalid_account_balance_api():
    client = TestClient(app)
    res = client.get(
        "/api/v1/trade-plan",
        params={
            "exchange": "binance",
            "market_type": "spot",
            "symbol": "BTC/USDT",
            "account_balance": -1,
        },
    )
    assert res.status_code == 422


def test_api_trade_plan_schema(monkeypatch):
    from app.analysis.trade_plan.models import (
        EligibilityResult,
        TradePlanDataQuality,
        ValidationResult,
    )
    from app.api.schemas.trade_plan import TradePlanResponse

    async def fake_compute(**_kwargs):
        return TradePlanResponse(
            exchange=ExchangeId.BINANCE,
            symbol="BTC/USDT",
            market_type=MarketType.SPOT,
            plan_id="tp_test",
            direction=None,
            plan_status="blocked",
            entry=None,
            stop_loss=None,
            take_profit_targets=[],
            risk=None,
            position_sizing=None,
            validation=ValidationResult(
                is_valid=False,
                validation_errors=["blocked"],
                warnings=[],
                blocking_reasons=["blocked"],
            ),
            eligibility=EligibilityResult(
                is_eligible=False,
                direction=None,
                blocking_reasons=["blocked"],
            ),
            supporting_evidence_ids=[],
            conflict_ids=[],
            invalidation_conditions=[],
            explanations=["blocked"],
            configuration_version="trade-plan-v1.0.0-balanced",
            analysis_timestamp=NOW,
            data_quality=TradePlanDataQuality(
                overall="ready",
                is_analysis_complete=True,
                current_price=100.0,
                atr_available=True,
            ),
            confluence_assessment="mixed",
            confluence_assessment_strength="none",
            bullish_score=40,
            bearish_score=40,
            spot_short_warning=None,
            analysis_only_disclaimer=(
                "Analysis only — no orders are executed. "
                "Prices are analytical levels, not guaranteed fills."
            ),
            config={},
            data_source="binance:spot",
            metadata={"no_order_execution": True},
        )

    monkeypatch.setattr(
        "app.api.routes.trade_plan.compute_trade_plan_response",
        fake_compute,
    )
    client = TestClient(app)
    res = client.get(
        "/api/v1/trade-plan",
        params={"exchange": "binance", "market_type": "spot", "symbol": "BTC/USDT"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["configuration_version"] == "trade-plan-v1.0.0-balanced"
    assert body["plan_status"] == "blocked"
    assert "LONG" not in res.text
    assert "NO TRADE" not in res.text


def test_config_version():
    assert DEFAULT_TRADE_PLAN_CONFIG.config_version == "trade-plan-v1.0.0-balanced"
    other = TradePlanConfig(config_version="trade-plan-test")
    assert other.config_version == "trade-plan-test"


def test_analyze_trade_plan_blocked_without_setup():
    result = analyze_trade_plan(
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        confluence=_confluence(),
        mtf_snapshot=_mtf_ready(),
        bundles={},
        candles_by_tf={Timeframe.M15: [_candle(i, close=100 + (i % 3)) for i in range(30)]},
        account_balance=10_000,
        risk_percent=1.0,
        as_of=NOW,
    )
    assert result.plan_status == "blocked"
    assert result.eligibility.is_eligible
    assert result.configuration_version == "trade-plan-v1.0.0-balanced"
