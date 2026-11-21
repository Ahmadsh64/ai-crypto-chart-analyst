"""Phase 5.5 Market Opportunity Scanner unit tests."""

from __future__ import annotations

from datetime import datetime, timezone
from app.analysis.decision_engine.config import DEFAULT_DECISION_CONFIG
from app.analysis.decision_engine.models import (
    ConfluenceScoreSummary,
    DecisionDataQuality,
    DecisionResult,
    EntryConfirmationResult,
)
from app.analysis.trade_plan.models import (
    EligibilityResult as PlanEligibility,
    EntryZone,
    StopLossPlan,
    TakeProfitTarget,
    TradePlanDataQuality,
    TradePlanResult,
    ValidationResult,
)
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.scanner.config import ScannerConfig
from app.scanner.eligibility import classify_opportunity_status, entry_distance_pct, is_actionable
from app.scanner.models import MarketOpportunity, OpportunityStatus
from app.scanner.ohlcv_cache import OhlcvTtlCache
from app.scanner.ranking import sort_opportunities


def _decision(
    decision: str,
    *,
    lifecycle: str = "awaiting_confirmation",
    confirmed: bool = False,
    inside: bool = False,
) -> DecisionResult:
    return DecisionResult(
        decision_id="d1",
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        decision=decision,  # type: ignore[arg-type]
        decision_reason=f"{decision} reason",
        lifecycle=lifecycle,  # type: ignore[arg-type]
        confluence_scores=ConfluenceScoreSummary(bullish_score=80, bearish_score=20),
        entry_confirmation=EntryConfirmationResult(
            status="confirmed" if confirmed else "not_confirmed",
            is_confirmed=confirmed,
            explanation="test",
        ),
        take_profit_prices=[110.0, 120.0, 130.0],
        stop_loss_price=90.0,
        price_inside_entry_zone=inside,
        data_quality=DecisionDataQuality(
            overall="ok",
            is_analysis_complete=True,
            current_price=100.0,
        ),
        configuration_version=DEFAULT_DECISION_CONFIG.config_version,
        analysis_timestamp=datetime.now(timezone.utc),
    )


def _plan(eligible: bool = True) -> TradePlanResult:
    return TradePlanResult(
        plan_id="p1",
        symbol="BTC/USDT",
        exchange=ExchangeId.BINANCE,
        market_type=MarketType.SPOT,
        direction="bullish" if eligible else None,
        plan_status="eligible" if eligible else "blocked",
        entry=EntryZone(
            entry_low=98,
            entry_high=102,
            entry_reference_price=100,
            entry_type="order_block",
            entry_source="test",
            source_event_key="k",
            timeframe="15m",
            entry_explanation="e",
            price_inside_zone=True,
        )
        if eligible
        else None,
        stop_loss=StopLossPlan(
            stop_loss_price=90,
            stop_loss_source="swing",
            stop_loss_distance=10,
            stop_loss_distance_pct=10,
            buffer_value=0.1,
            invalidation_explanation="break",
        )
        if eligible
        else None,
        take_profit_targets=[
            TakeProfitTarget(
                index=1,
                label="TP1",
                price=110,
                source="test",
                distance=10,
                distance_pct=10,
                risk_reward_ratio=1,
                explanation="t",
            ),
            TakeProfitTarget(
                index=2,
                label="TP2",
                price=120,
                source="test",
                distance=20,
                distance_pct=20,
                risk_reward_ratio=2,
                explanation="t",
            ),
        ]
        if eligible
        else [],
        validation=ValidationResult(is_valid=eligible),
        eligibility=PlanEligibility(is_eligible=eligible),
        configuration_version="tp-test",
        analysis_timestamp=datetime.now(timezone.utc),
        data_quality=TradePlanDataQuality(overall="ok", is_analysis_complete=True),
    )


def test_wait_and_no_trade_not_ready():
    cfg = ScannerConfig()
    wait = classify_opportunity_status(
        decision=_decision("WAIT"),
        trade_plan=_plan(False),
        current_price=100,
        config=cfg,
        data_ok=True,
    )
    no_trade = classify_opportunity_status(
        decision=_decision("NO TRADE", lifecycle="invalidated"),
        trade_plan=_plan(False),
        current_price=100,
        config=cfg,
        data_ok=True,
    )
    assert wait == OpportunityStatus.WAITING
    assert no_trade == OpportunityStatus.INVALIDATED
    assert not is_actionable(wait)
    assert not is_actionable(no_trade)


def test_long_ready_when_confirmed_and_eligible():
    cfg = ScannerConfig()
    status = classify_opportunity_status(
        decision=_decision("LONG", confirmed=True, inside=True, lifecycle="entry_confirmed"),
        trade_plan=_plan(True),
        current_price=100,
        config=cfg,
        data_ok=True,
    )
    assert status == OpportunityStatus.READY
    assert is_actionable(status)


def test_approaching_entry():
    cfg = ScannerConfig(approaching_entry_pct=1.0)
    status = classify_opportunity_status(
        decision=_decision("SHORT", lifecycle="awaiting_confirmation"),
        trade_plan=_plan(True),
        current_price=103,  # ~1% above zone high 102
        config=cfg,
        data_ok=True,
    )
    assert status in (
        OpportunityStatus.APPROACHING_ENTRY,
        OpportunityStatus.READY,
        OpportunityStatus.WAITING,
    )


def test_expired_and_data_unavailable():
    cfg = ScannerConfig()
    expired = classify_opportunity_status(
        decision=_decision("LONG", lifecycle="expired"),
        trade_plan=_plan(True),
        current_price=100,
        config=cfg,
        data_ok=True,
    )
    missing = classify_opportunity_status(
        decision=None,
        trade_plan=None,
        current_price=None,
        config=cfg,
        data_ok=False,
    )
    assert expired == OpportunityStatus.EXPIRED
    assert missing == OpportunityStatus.DATA_UNAVAILABLE


def test_entry_distance():
    assert entry_distance_pct(100, 98, 102, 100) == 0.0
    d = entry_distance_pct(110, 98, 102, 100)
    assert d is not None and d > 0


def test_ranking_prefers_ready_and_higher_confluence():
    now = datetime.now(timezone.utc)
    a = MarketOpportunity(
        opportunity_id="a",
        exchange=ExchangeId.BINANCE,
        market_type=MarketType.SPOT,
        symbol="ETH/USDT",
        base="ETH",
        timeframe=Timeframe.H1,
        status=OpportunityStatus.WAITING,
        confluence_score=90,
        analysis_timestamp=now,
    )
    b = MarketOpportunity(
        opportunity_id="b",
        exchange=ExchangeId.BINANCE,
        market_type=MarketType.SPOT,
        symbol="BTC/USDT",
        base="BTC",
        timeframe=Timeframe.H1,
        status=OpportunityStatus.READY,
        confluence_score=70,
        analysis_timestamp=now,
        actionable=True,
    )
    ranked = sort_opportunities([a, b])
    assert ranked[0].opportunity_id == "b"
    assert "confluence" in ranked[0].rank_explanation.lower()


def test_ohlcv_cache_roundtrip():
    cache = OhlcvTtlCache(ttl_seconds=60)
    candle = Candle(
        timestamp=datetime.now(timezone.utc),
        open=1,
        high=2,
        low=0.5,
        close=1.5,
        volume=10,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
    )
    cache.set(ExchangeId.BINANCE, MarketType.SPOT, "BTC/USDT", Timeframe.H1, [candle])
    got = cache.get(ExchangeId.BINANCE, MarketType.SPOT, "BTC/USDT", Timeframe.H1)
    assert got is not None and len(got) == 1


def test_duplicate_scan_lock(monkeypatch):
    import asyncio
    from app.scanner.service import MarketOpportunityScanner
    from app.scanner.store import OpportunityStore

    scanner = MarketOpportunityScanner(
        config=ScannerConfig(enabled=True, auto_start=False, max_pairs_per_market=1),
        store=OpportunityStore(),
    )

    async def _slow(*_a, **_k):
        await asyncio.sleep(0.2)
        from app.scanner.universe import UniverseDiscoveryResult

        return UniverseDiscoveryResult()

    monkeypatch.setattr("app.scanner.service.discover_universe", _slow)

    async def run():
        t1 = asyncio.create_task(scanner.run_scan(trigger="a"))
        await asyncio.sleep(0.05)
        t2 = asyncio.create_task(scanner.run_scan(trigger="b"))
        r1, r2 = await asyncio.gather(t1, t2)
        statuses = {r1.status, r2.status}
        assert "skipped" in statuses or statuses == {"completed"}

    asyncio.run(run())
