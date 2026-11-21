"""Phase 5.5.1.1 — WAIT + eligible plan level visibility tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.scanner.analyze import analyze_candidate
from app.scanner.config import ScannerConfig
from app.scanner.eligibility import is_actionable
from app.scanner.models import OpportunityStatus
from app.scanner.ohlcv_cache import OhlcvTtlCache
from app.scanner.store import OpportunityStore
from app.scanner.universe import ScanCandidate
from app.api.routes.opportunities import _filter_sort


def _candles(tf: Timeframe, market_type: MarketType) -> list[Candle]:
    ts = datetime.now(timezone.utc)
    return [
        Candle(
            timestamp=ts,
            open=0.05,
            high=0.06,
            low=0.04,
            close=0.0545,
            volume=1.0,
            exchange=ExchangeId.BINANCE,
            symbol="DOGE/USDT",
            market_type=market_type,
            is_closed=True,
        )
    ]


def _plan(*, direction: str = "bearish", eligible: bool = True):
    plan = MagicMock()
    plan.plan_status = "eligible" if eligible else "blocked"
    plan.direction = direction if eligible else None
    plan.plan_id = "plan-1"
    if eligible:
        plan.entry = MagicMock(
            entry_low=0.0537,
            entry_high=0.0539,
            entry_reference_price=0.0538,
        )
        plan.stop_loss = MagicMock(stop_loss_price=0.0541)
        plan.take_profit_targets = [
            MagicMock(index=1, price=0.0532),
            MagicMock(index=2, price=0.0528),
            MagicMock(index=3, price=0.0524),
        ]
        plan.risk = MagicMock(primary_rr=2.07, meets_minimum_rr=True)
    else:
        plan.entry = None
        plan.stop_loss = None
        plan.take_profit_targets = []
        plan.risk = None
    plan.eligibility = MagicMock(blocking_reasons=[])
    plan.validation = MagicMock(blocking_reasons=[])
    plan.supporting_evidence_ids = []
    plan.data_quality = MagicMock(limitations=[])
    return plan


def _decision(
    *,
    decision: str = "WAIT",
    lifecycle: str = "awaiting_confirmation",
    confirmed: bool = False,
    inside: bool = False,
):
    dec = MagicMock()
    dec.decision = decision
    dec.decision_reason = f"{decision}: fixture reason"
    dec.lifecycle = lifecycle
    dec.confluence_scores = MagicMock(
        bullish_score=35.0,
        bearish_score=73.7,
        preliminary_assessment="bearish_confluence",
        assessment_strength="strong",
    )
    dec.entry_confirmation = MagicMock(
        status="confirmed" if confirmed else "not_confirmed",
        is_confirmed=confirmed,
        blocking_reasons=[] if confirmed else ["5M entry confirmation not present."],
        explanation="fixture",
    )
    dec.take_profit_prices = [0.0532, 0.0528, 0.0524]
    dec.primary_rr = 2.07
    dec.supporting_evidence = ["fixture evidence"]
    dec.blocking_conditions = (
        ["5M entry confirmation not present."] if decision == "WAIT" else []
    )
    dec.data_quality = MagicMock(is_analysis_complete=True, current_price=0.0545)
    dec.analysis_timestamp = datetime.now(timezone.utc)
    dec.decision_id = "d-fixture"
    dec.trade_plan_id = "p-fixture"
    dec.price_inside_entry_zone = inside
    return dec


async def _run(
    *,
    market_type: MarketType,
    decision: str,
    plan_direction: str,
    eligible: bool,
    confirmed: bool = False,
    inside: bool = False,
    lifecycle: str = "awaiting_confirmation",
):
    candidate = ScanCandidate(
        exchange=ExchangeId.BINANCE,
        market_type=market_type,
        symbol="DOGE/USDT",
        base="DOGE",
        quote_volume_24h=1e8,
    )
    cfg = ScannerConfig(auto_start=False)
    cache = OhlcvTtlCache(60)

    async def fake_load(**_k):
        return {
            tf: _candles(tf, market_type)
            for tf in (Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5)
        }

    import app.scanner.analyze as mod

    plan = _plan(direction=plan_direction, eligible=eligible)
    dec = _decision(
        decision=decision,
        lifecycle=lifecycle,
        confirmed=confirmed,
        inside=inside,
    )
    candles = {
        tf: _candles(tf, market_type)
        for tf in (Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5)
    }

    # Patch heavy path
    orig_load = mod.load_mtf_candles
    orig_ctx = mod.build_analysis_context_from_candles
    orig_plan = mod.analyze_trade_plan
    orig_dec = mod.analyze_decision
    mod.load_mtf_candles = fake_load  # type: ignore[assignment]
    mod.build_analysis_context_from_candles = lambda *_a, **_k: MagicMock(  # type: ignore[assignment]
        confluence=MagicMock(),
        mtf_snapshot=MagicMock(),
        bundles={},
        candles_by_tf=candles,
        as_of=datetime.now(timezone.utc),
    )
    mod.analyze_trade_plan = lambda **_k: plan  # type: ignore[assignment]
    mod.analyze_decision = lambda **_k: dec  # type: ignore[assignment]
    try:
        return await analyze_candidate(
            candidate,
            config=cfg,
            cache=cache,
            execution_timeframe=Timeframe.M15,
        )
    finally:
        mod.load_mtf_candles = orig_load
        mod.build_analysis_context_from_candles = orig_ctx
        mod.analyze_trade_plan = orig_plan
        mod.analyze_decision = orig_dec


@pytest.mark.asyncio
async def test_a_eligible_long_wait_exposes_levels():
    opp = await _run(
        market_type=MarketType.SPOT,
        decision="WAIT",
        plan_direction="bullish",
        eligible=True,
    )
    assert opp.decision == "WAIT"
    assert opp.status == OpportunityStatus.WAITING
    assert opp.actionable is False
    assert is_actionable(opp.status) is False
    assert opp.direction is not None and opp.direction.value == "LONG"
    assert opp.entry_reference == 0.0538
    assert opp.entry_low == 0.0537
    assert opp.stop_loss == 0.0541
    assert opp.take_profits[0].available is True
    assert opp.primary_rr == 2.07


@pytest.mark.asyncio
async def test_b_eligible_short_wait_futures_exposes_levels():
    opp = await _run(
        market_type=MarketType.USDT_M_FUTURES,
        decision="WAIT",
        plan_direction="bearish",
        eligible=True,
    )
    assert opp.decision == "WAIT"
    assert opp.status == OpportunityStatus.WAITING
    assert opp.actionable is False
    assert opp.direction.value == "SHORT"
    assert opp.market_executable is True
    assert opp.entry_reference == 0.0538
    assert opp.primary_rr == 2.07


@pytest.mark.asyncio
async def test_c_spot_bearish_non_executable():
    opp = await _run(
        market_type=MarketType.SPOT,
        decision="WAIT",
        plan_direction="bearish",
        eligible=True,
    )
    assert opp.decision == "WAIT"
    assert opp.direction.value == "SHORT"
    assert opp.actionable is False
    assert opp.market_executable is False
    assert "Spot" in opp.executability_note
    assert opp.entry_low is not None


@pytest.mark.asyncio
async def test_d_confirmed_long_ready():
    opp = await _run(
        market_type=MarketType.SPOT,
        decision="LONG",
        plan_direction="bullish",
        eligible=True,
        confirmed=True,
        inside=True,
        lifecycle="entry_confirmed",
    )
    assert opp.decision == "LONG"
    assert opp.status == OpportunityStatus.READY
    assert opp.actionable is True
    assert opp.direction.value == "LONG"
    assert opp.entry_reference is not None


@pytest.mark.asyncio
async def test_e_confirmed_short_futures_ready():
    opp = await _run(
        market_type=MarketType.LINEAR_PERPETUAL,
        decision="SHORT",
        plan_direction="bearish",
        eligible=True,
        confirmed=True,
        inside=True,
        lifecycle="entry_confirmed",
    )
    assert opp.decision == "SHORT"
    assert opp.status == OpportunityStatus.READY
    assert opp.actionable is True
    assert opp.market_executable is True


@pytest.mark.asyncio
async def test_f_wait_without_eligible_plan_no_invented_levels():
    opp = await _run(
        market_type=MarketType.SPOT,
        decision="WAIT",
        plan_direction="bearish",
        eligible=False,
        lifecycle="setup_detected",
    )
    assert opp.decision == "WAIT"
    assert opp.entry_reference is None
    assert opp.stop_loss is None
    assert all(not t.available for t in opp.take_profits)
    assert opp.primary_rr is None
    assert opp.direction is None


@pytest.mark.asyncio
async def test_g_no_trade_without_plan_no_levels():
    opp = await _run(
        market_type=MarketType.SPOT,
        decision="NO TRADE",
        plan_direction="bearish",
        eligible=False,
        lifecycle="invalidated",
    )
    assert opp.decision == "NO TRADE"
    assert opp.entry_reference is None
    assert all(not t.available for t in opp.take_profits)


@pytest.mark.asyncio
async def test_h_direction_filter_includes_waiting_planned_short():
    wait_short = await _run(
        market_type=MarketType.USDT_M_FUTURES,
        decision="WAIT",
        plan_direction="bearish",
        eligible=True,
    )
    ready_long = await _run(
        market_type=MarketType.SPOT,
        decision="LONG",
        plan_direction="bullish",
        eligible=True,
        confirmed=True,
        inside=True,
        lifecycle="entry_confirmed",
    )
    filtered = _filter_sort(
        [wait_short, ready_long],
        exchange=None,
        market_type=None,
        timeframe=None,
        direction="SHORT",
        status=None,
        search=None,
        actionable_only=False,
        sort="rank",
    )
    assert len(filtered) == 1
    assert filtered[0].decision == "WAIT"
    assert filtered[0].direction.value == "SHORT"


@pytest.mark.asyncio
async def test_i_ready_counts_exclude_waiting():
    store = OpportunityStore()
    wait = await _run(
        market_type=MarketType.SPOT,
        decision="WAIT",
        plan_direction="bearish",
        eligible=True,
    )
    ready = await _run(
        market_type=MarketType.SPOT,
        decision="LONG",
        plan_direction="bullish",
        eligible=True,
        confirmed=True,
        inside=True,
        lifecycle="entry_confirmed",
    )
    store.replace_opportunities([wait, ready])
    store.set_state("idle")
    st = store.status()
    assert st.ready_opportunities == 1
    assert st.waiting_opportunities == 1
    assert st.qualified_opportunities == 1
    assert st.long_opportunities == 1


@pytest.mark.asyncio
async def test_j_repeated_scan_same_fingerprint_stable_id():
    a = await _run(
        market_type=MarketType.SPOT,
        decision="WAIT",
        plan_direction="bearish",
        eligible=True,
    )
    b = await _run(
        market_type=MarketType.SPOT,
        decision="WAIT",
        plan_direction="bearish",
        eligible=True,
    )
    assert a.opportunity_id == b.opportunity_id
    assert a.metadata.get("setup_fingerprint") == b.metadata.get("setup_fingerprint")
