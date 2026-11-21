"""Phase 5.5 Step 1 — execution-timeframe matrix tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.analysis.decision_engine.config import DEFAULT_DECISION_CONFIG
from app.analysis.multi_timeframe.config import MTF_LADDER
from app.analysis.trade_plan.config import DEFAULT_TRADE_PLAN_CONFIG
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.scanner.analyze import analyze_candidate, load_mtf_candles
from app.scanner.config import ScannerConfig
from app.scanner.execution_timeframes import (
    EXECUTION_TIMEFRAMES,
    REQUIRED_MTF_LADDER,
    decision_config_for_execution,
    get_execution_overlay,
    opportunity_id_for,
    trade_plan_config_for_execution,
)
from app.scanner.ohlcv_cache import OhlcvTtlCache
from app.scanner.service import MarketOpportunityScanner
from app.scanner.store import OpportunityStore
from app.scanner.universe import ScanCandidate


def test_four_execution_timeframes_defined():
    assert EXECUTION_TIMEFRAMES == (
        Timeframe.M5,
        Timeframe.M15,
        Timeframe.H1,
        Timeframe.H4,
    )
    assert REQUIRED_MTF_LADDER == MTF_LADDER
    assert set(REQUIRED_MTF_LADDER) == {
        Timeframe.H4,
        Timeframe.H1,
        Timeframe.M15,
        Timeframe.M5,
    }


def test_overlay_mapping_per_execution_tf():
    expected = {
        Timeframe.M5: (Timeframe.M5, Timeframe.M5),
        Timeframe.M15: (Timeframe.M15, Timeframe.M5),
        Timeframe.H1: (Timeframe.H1, Timeframe.M15),
        Timeframe.H4: (Timeframe.H4, Timeframe.H1),
    }
    for exec_tf, (setup, confirm) in expected.items():
        overlay = get_execution_overlay(exec_tf)
        assert overlay.setup_timeframe == setup
        assert overlay.confirmation_timeframe == confirm


def test_overlays_preserve_eligibility_thresholds():
    for tf in EXECUTION_TIMEFRAMES:
        dcfg = decision_config_for_execution(tf)
        tcfg = trade_plan_config_for_execution(tf)
        assert dcfg.min_directional_score == DEFAULT_DECISION_CONFIG.min_directional_score
        assert dcfg.min_score_margin == DEFAULT_DECISION_CONFIG.min_score_margin
        assert dcfg.minimum_primary_rr == DEFAULT_DECISION_CONFIG.minimum_primary_rr
        assert dcfg.require_assessment_strength == DEFAULT_DECISION_CONFIG.require_assessment_strength
        assert dcfg.block_critical_conflicts == DEFAULT_DECISION_CONFIG.block_critical_conflicts
        assert dcfg.require_5m_confirmation is True
        assert set(dcfg.required_timeframes) == set(REQUIRED_MTF_LADDER)

        assert tcfg.min_directional_score == DEFAULT_TRADE_PLAN_CONFIG.min_directional_score
        assert tcfg.min_score_margin == DEFAULT_TRADE_PLAN_CONFIG.min_score_margin
        assert tcfg.minimum_primary_target_rr == DEFAULT_TRADE_PLAN_CONFIG.minimum_primary_target_rr
        assert tcfg.require_assessment_strength == DEFAULT_TRADE_PLAN_CONFIG.require_assessment_strength
        assert tcfg.block_critical_conflicts == DEFAULT_TRADE_PLAN_CONFIG.block_critical_conflicts
        assert set(REQUIRED_MTF_LADDER).issubset(set(tcfg.required_timeframes))


def test_opportunity_ids_independent_per_timeframe():
    ids = [
        opportunity_id_for(
            ExchangeId.BINANCE, MarketType.SPOT, "BTC/USDT", tf
        )
        for tf in EXECUTION_TIMEFRAMES
    ]
    assert len(ids) == 4
    assert len(set(ids)) == 4
    # Same setup again → same id (stable across refresh)
    assert ids[0] == opportunity_id_for(
        ExchangeId.BINANCE, MarketType.SPOT, "BTC/USDT", Timeframe.M5
    )


def test_opportunity_ids_differ_by_market_and_exchange():
    a = opportunity_id_for(ExchangeId.BINANCE, MarketType.SPOT, "BTC/USDT", Timeframe.H1)
    b = opportunity_id_for(
        ExchangeId.BINANCE, MarketType.USDT_M_FUTURES, "BTC/USDT", Timeframe.H1
    )
    c = opportunity_id_for(ExchangeId.BYBIT, MarketType.SPOT, "BTC/USDT", Timeframe.H1)
    assert len({a, b, c}) == 3


def _fake_candles(tf: Timeframe, n: int = 80) -> list[Candle]:
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    step = {
        Timeframe.M5: timedelta(minutes=5),
        Timeframe.M15: timedelta(minutes=15),
        Timeframe.H1: timedelta(hours=1),
        Timeframe.H4: timedelta(hours=4),
    }[tf]
    out: list[Candle] = []
    price = 100.0
    for i in range(n):
        ts = now - step * (n - i)
        out.append(
            Candle(
                timestamp=ts,
                open=price,
                high=price + 1,
                low=price - 1,
                close=price + 0.2,
                volume=1000.0,
                exchange=ExchangeId.BINANCE,
                symbol="BTC/USDT",
                market_type=MarketType.SPOT,
                is_closed=True,
            )
        )
        price += 0.1
    return out


@pytest.mark.asyncio
async def test_load_mtf_candles_fetches_full_ladder(monkeypatch):
    fetched: list[Timeframe] = []

    async def fake_ohlcv(exchange, symbol, timeframe, market_type, limit=None):
        fetched.append(timeframe)
        return _fake_candles(timeframe)

    manager = MagicMock()
    manager.fetch_ohlcv = AsyncMock(side_effect=fake_ohlcv)
    monkeypatch.setattr("app.scanner.analyze.get_exchange_manager", lambda: manager)

    cache = OhlcvTtlCache(ttl_seconds=60)
    candles = await load_mtf_candles(
        exchange=ExchangeId.BINANCE,
        market_type=MarketType.SPOT,
        symbol="BTC/USDT",
        cache=cache,
    )
    assert set(fetched) == set(MTF_LADDER)
    assert set(candles.keys()) == set(MTF_LADDER)

    # Second call uses cache — no additional fetches
    fetched.clear()
    await load_mtf_candles(
        exchange=ExchangeId.BINANCE,
        market_type=MarketType.SPOT,
        symbol="BTC/USDT",
        cache=cache,
    )
    assert fetched == []


@pytest.mark.asyncio
async def test_analyze_candidate_uses_execution_overlay_and_labels_tf(monkeypatch):
    """Each execution TF gets its own overlay configs and opportunity timeframe."""
    seen_setup: list[Timeframe] = []
    seen_confirm: list[Timeframe] = []

    async def fake_load(**_kwargs):
        return {tf: _fake_candles(tf) for tf in MTF_LADDER}

    monkeypatch.setattr("app.scanner.analyze.load_mtf_candles", fake_load)

    # Minimal context stub — bypass heavy SMC by mocking context + engines
    ctx = MagicMock()
    ctx.confluence = MagicMock()
    ctx.mtf_snapshot = MagicMock()
    ctx.bundles = {}
    ctx.candles_by_tf = {tf: _fake_candles(tf) for tf in MTF_LADDER}
    ctx.as_of = datetime.now(timezone.utc)
    monkeypatch.setattr(
        "app.scanner.analyze.build_analysis_context_from_candles",
        lambda *_a, **_k: ctx,
    )

    def fake_plan(**kwargs):
        cfg = kwargs["config"]
        seen_setup.append(cfg.setup_timeframe)
        seen_confirm.append(cfg.confirmation_timeframe)
        plan = MagicMock()
        plan.plan_status = "blocked"
        plan.entry = None
        plan.stop_loss = None
        plan.take_profit_targets = []
        plan.plan_id = f"plan-{cfg.setup_timeframe.value}"
        return plan

    def fake_decision(**kwargs):
        cfg = kwargs["config"]
        # Distinct decision labels prove independence by setup TF
        decision_by_setup = {
            Timeframe.M5: "WAIT",
            Timeframe.M15: "NO TRADE",
            Timeframe.H1: "WAIT",
            Timeframe.H4: "NO TRADE",
        }
        dec = MagicMock()
        dec.decision = decision_by_setup[cfg.setup_timeframe]
        dec.decision_reason = f"setup={cfg.setup_timeframe.value}"
        dec.lifecycle = "awaiting_confirmation"
        dec.confluence_scores = MagicMock(bullish_score=40.0, bearish_score=30.0)
        dec.entry_confirmation = MagicMock(status="not_confirmed")
        dec.take_profit_prices = []
        dec.primary_rr = None
        dec.supporting_evidence = []
        dec.blocking_conditions = ["fixture"]
        dec.data_quality = MagicMock(is_analysis_complete=True, current_price=100.0)
        dec.analysis_timestamp = datetime.now(timezone.utc)
        dec.decision_id = f"d-{cfg.setup_timeframe.value}"
        dec.trade_plan_id = f"p-{cfg.setup_timeframe.value}"
        return dec

    monkeypatch.setattr("app.scanner.analyze.analyze_trade_plan", fake_plan)
    monkeypatch.setattr("app.scanner.analyze.analyze_decision", fake_decision)

    candidate = ScanCandidate(
        exchange=ExchangeId.BINANCE,
        market_type=MarketType.SPOT,
        symbol="BTC/USDT",
        base="BTC",
        quote_volume_24h=1_000_000.0,
    )
    cfg = ScannerConfig(auto_start=False)
    cache = OhlcvTtlCache(60)

    results = []
    for tf in EXECUTION_TIMEFRAMES:
        opp = await analyze_candidate(
            candidate, config=cfg, cache=cache, execution_timeframe=tf
        )
        results.append(opp)

    assert [o.timeframe for o in results] == list(EXECUTION_TIMEFRAMES)
    assert len({o.opportunity_id for o in results}) == 4
    assert [o.decision for o in results] == ["WAIT", "NO TRADE", "WAIT", "NO TRADE"]
    assert seen_setup == [Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4]
    assert seen_confirm == [Timeframe.M5, Timeframe.M5, Timeframe.M15, Timeframe.H1]
    for opp in results:
        assert opp.metadata["mtf_ladder"] == [tf.value for tf in MTF_LADDER]


@pytest.mark.asyncio
async def test_scanner_matrix_emits_four_opportunities_per_pair(monkeypatch):
    candidate = ScanCandidate(
        exchange=ExchangeId.BINANCE,
        market_type=MarketType.SPOT,
        symbol="ETH/USDT",
        base="ETH",
    )

    async def fake_discover(_config):
        return [candidate]

    calls: list[Timeframe] = []

    async def fake_analyze(cand, *, config, cache, execution_timeframe):
        calls.append(execution_timeframe)
        from app.scanner.models import MarketOpportunity, OpportunityStatus

        return MarketOpportunity(
            opportunity_id=opportunity_id_for(
                cand.exchange, cand.market_type, cand.symbol, execution_timeframe
            ),
            exchange=cand.exchange,
            market_type=cand.market_type,
            symbol=cand.symbol,
            base=cand.base,
            timeframe=execution_timeframe,
            status=OpportunityStatus.WAITING,
            decision="WAIT",
            actionable=False,
        )

    async def fake_universe(_config):
        from app.scanner.universe import UniverseDiscoveryResult

        return UniverseDiscoveryResult(
            candidates=[candidate],
            discovered_pairs=1,
            eligible_pairs=1,
            selected_pairs=1,
        )

    monkeypatch.setattr("app.scanner.service.discover_universe", fake_universe)
    monkeypatch.setattr("app.scanner.service.analyze_candidate", fake_analyze)

    scanner = MarketOpportunityScanner(
        config=ScannerConfig(enabled=True, auto_start=False, max_pairs_per_market=1),
        store=OpportunityStore(),
    )
    summary = await scanner.run_scan(trigger="test")
    assert summary.status == "completed"
    assert summary.pairs_scanned == 1  # one pair fully completed across all TFs
    assert summary.timeframe_analyses_attempted == 4
    assert summary.timeframe_analyses_completed == 4
    assert summary.opportunities_found == 4
    assert set(calls) == set(EXECUTION_TIMEFRAMES)
    stored = scanner.store.list_opportunities()
    assert len(stored) == 4
    assert {o.timeframe for o in stored} == set(EXECUTION_TIMEFRAMES)
