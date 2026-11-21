"""Phase 5.5 Step 2 — universe expansion and staged scanning tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.exchanges.types import ExchangeId, MarketType, Ticker, TradingPair
from app.scanner.config import ScannerConfig
from app.scanner.execution_timeframes import EXECUTION_TIMEFRAMES
from app.scanner.models import MarketOpportunity, OpportunityStatus
from app.scanner.service import MarketOpportunityScanner
from app.scanner.store import OpportunityStore
from app.scanner.universe import (
    RANKING_METHOD,
    ScanCandidate,
    UniverseDiscoveryResult,
    discover_universe,
)


def _pair(
    symbol: str,
    *,
    exchange: ExchangeId = ExchangeId.BINANCE,
    market_type: MarketType = MarketType.SPOT,
    active: bool = True,
    quote: str = "USDT",
) -> TradingPair:
    base = symbol.split("/")[0]
    return TradingPair(
        symbol=symbol,
        base=base,
        quote=quote,
        exchange=exchange,
        market_type=market_type,
        native_symbol=symbol.replace("/", ""),
        active=active,
    )


def _ticker(symbol: str, volume: float | None, market_type: MarketType = MarketType.SPOT) -> Ticker:
    return Ticker(
        symbol=symbol,
        exchange=ExchangeId.BINANCE,
        market_type=market_type,
        last=1.0,
        volume_24h=volume,
        updated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_volume_ranking_and_25_cap(monkeypatch):
    pairs = [_pair(f"C{i}/USDT") for i in range(40)]
    # Higher index → higher volume so ranking is deterministic
    tickers = [_ticker(f"C{i}/USDT", float(i + 1) * 1_000_000) for i in range(40)]

    manager = MagicMock()
    manager.list_exchanges.return_value = [
        MagicMock(id=ExchangeId.BINANCE, market_types=[MarketType.SPOT]),
    ]
    manager.list_markets = AsyncMock(return_value=pairs)
    manager.fetch_tickers_24h = AsyncMock(return_value=tickers)
    monkeypatch.setattr("app.scanner.universe.get_exchange_manager", lambda: manager)

    cache = MagicMock()
    cache.get.return_value = None
    cache.set = MagicMock()
    monkeypatch.setattr("app.scanner.universe.get_markets_cache", lambda: cache)

    cfg = ScannerConfig(
        default_exchanges=[ExchangeId.BINANCE],
        default_market_types=[MarketType.SPOT],
        max_pairs_per_market=25,
        min_quote_volume_24h=500_000,
        ticker_prefetch=True,
    )
    result = await discover_universe(cfg)
    assert result.discovered_pairs == 40
    assert result.eligible_pairs == 40
    assert result.selected_pairs == 25
    assert len(result.candidates) == 25
    # Top by volume: C39 … C15
    assert result.candidates[0].symbol == "C39/USDT"
    assert result.candidates[-1].symbol == "C15/USDT"
    assert result.ranking_method == RANKING_METHOD
    assert any(e.reason == "over_cap" for e in result.excluded)


@pytest.mark.asyncio
async def test_fewer_than_25_eligible(monkeypatch):
    pairs = [_pair("AAA/USDT"), _pair("BBB/USDT"), _pair("CCC/USDT")]
    tickers = [
        _ticker("AAA/USDT", 2_000_000),
        _ticker("BBB/USDT", 1_500_000),
        _ticker("CCC/USDT", 1_000_000),
    ]
    manager = MagicMock()
    manager.list_exchanges.return_value = [
        MagicMock(id=ExchangeId.BINANCE, market_types=[MarketType.SPOT]),
    ]
    manager.list_markets = AsyncMock(return_value=pairs)
    manager.fetch_tickers_24h = AsyncMock(return_value=tickers)
    monkeypatch.setattr("app.scanner.universe.get_exchange_manager", lambda: manager)
    cache = MagicMock()
    cache.get.return_value = None
    cache.set = MagicMock()
    monkeypatch.setattr("app.scanner.universe.get_markets_cache", lambda: cache)

    cfg = ScannerConfig(
        default_exchanges=[ExchangeId.BINANCE],
        default_market_types=[MarketType.SPOT],
        max_pairs_per_market=25,
    )
    result = await discover_universe(cfg)
    assert result.selected_pairs == 3
    assert len(result.candidates) == 3


@pytest.mark.asyncio
async def test_below_min_volume_and_missing_volume_excluded(monkeypatch):
    pairs = [_pair("LOW/USDT"), _pair("MISS/USDT"), _pair("OK/USDT"), _pair("NOTICK/USDT")]
    tickers = [
        _ticker("LOW/USDT", 100.0),  # below min
        _ticker("MISS/USDT", None),  # missing volume
        _ticker("OK/USDT", 2_000_000),
        # NOTICK absent from tickers
    ]
    manager = MagicMock()
    manager.list_exchanges.return_value = [
        MagicMock(id=ExchangeId.BINANCE, market_types=[MarketType.SPOT]),
    ]
    manager.list_markets = AsyncMock(return_value=pairs)
    manager.fetch_tickers_24h = AsyncMock(return_value=tickers)
    monkeypatch.setattr("app.scanner.universe.get_exchange_manager", lambda: manager)
    cache = MagicMock()
    cache.get.return_value = None
    cache.set = MagicMock()
    monkeypatch.setattr("app.scanner.universe.get_markets_cache", lambda: cache)

    cfg = ScannerConfig(
        default_exchanges=[ExchangeId.BINANCE],
        default_market_types=[MarketType.SPOT],
        min_quote_volume_24h=500_000,
    )
    result = await discover_universe(cfg)
    assert [c.symbol for c in result.candidates] == ["OK/USDT"]
    reasons = {e.symbol: e.reason for e in result.excluded if e.symbol}
    assert reasons["LOW/USDT"].startswith("below_min_volume")
    assert reasons["MISS/USDT"] == "missing_volume"
    assert reasons["NOTICK/USDT"] == "missing_ticker"


@pytest.mark.asyncio
async def test_inactive_and_non_usdt_filtered(monkeypatch):
    pairs = [
        _pair("BTC/USDT", active=True),
        _pair("ETH/USDT", active=False),
        _pair("AAA/BTC", quote="BTC", active=True),
    ]
    # Cache path returns already-listed; simulate list_markets returning mix
    manager = MagicMock()
    manager.list_exchanges.return_value = [
        MagicMock(id=ExchangeId.BINANCE, market_types=[MarketType.SPOT]),
    ]
    manager.list_markets = AsyncMock(return_value=pairs)
    manager.fetch_tickers_24h = AsyncMock(
        return_value=[_ticker("BTC/USDT", 10_000_000)]
    )
    monkeypatch.setattr("app.scanner.universe.get_exchange_manager", lambda: manager)
    cache = MagicMock()
    cache.get.return_value = None
    cache.set = MagicMock()
    monkeypatch.setattr("app.scanner.universe.get_markets_cache", lambda: cache)

    cfg = ScannerConfig(
        default_exchanges=[ExchangeId.BINANCE],
        default_market_types=[MarketType.SPOT],
    )
    result = await discover_universe(cfg)
    # Active filter drops ETH; discovered = BTC + AAA/BTC; USDT keeps BTC only.
    assert result.discovered_pairs == 2
    assert result.selected_pairs == 1
    assert result.candidates[0].symbol == "BTC/USDT"


@pytest.mark.asyncio
async def test_spot_and_futures_universes_separate(monkeypatch):
    calls: list[tuple[ExchangeId, MarketType]] = []

    async def fake_list(exchange, market_type):
        calls.append((exchange, market_type))
        return [_pair("BTC/USDT", exchange=exchange, market_type=market_type)]

    async def fake_tickers(exchange, market_type):
        return [
            Ticker(
                symbol="BTC/USDT",
                exchange=exchange,
                market_type=market_type,
                last=1.0,
                volume_24h=5_000_000,
                updated_at=datetime.now(timezone.utc),
            )
        ]

    manager = MagicMock()
    manager.list_exchanges.return_value = [
        MagicMock(
            id=ExchangeId.BINANCE,
            market_types=[MarketType.SPOT, MarketType.USDT_M_FUTURES],
        ),
        MagicMock(
            id=ExchangeId.BYBIT,
            market_types=[MarketType.SPOT, MarketType.LINEAR_PERPETUAL],
        ),
    ]
    manager.list_markets = AsyncMock(side_effect=fake_list)
    manager.fetch_tickers_24h = AsyncMock(side_effect=fake_tickers)
    monkeypatch.setattr("app.scanner.universe.get_exchange_manager", lambda: manager)
    cache = MagicMock()
    cache.get.return_value = None
    cache.set = MagicMock()
    monkeypatch.setattr("app.scanner.universe.get_markets_cache", lambda: cache)

    cfg = ScannerConfig(max_pairs_per_market=25)
    result = await discover_universe(cfg)
    assert len(calls) == 4
    assert set(calls) == {
        (ExchangeId.BINANCE, MarketType.SPOT),
        (ExchangeId.BINANCE, MarketType.USDT_M_FUTURES),
        (ExchangeId.BYBIT, MarketType.SPOT),
        (ExchangeId.BYBIT, MarketType.LINEAR_PERPETUAL),
    }
    assert result.selected_pairs == 4
    assert len(result.per_market) == 4


@pytest.mark.asyncio
async def test_binance_failure_does_not_block_bybit(monkeypatch):
    async def fake_list(exchange, market_type):
        if exchange == ExchangeId.BINANCE:
            raise RuntimeError("binance down")
        return [_pair("ETH/USDT", exchange=exchange, market_type=market_type)]

    async def fake_tickers(exchange, market_type):
        return [
            Ticker(
                symbol="ETH/USDT",
                exchange=exchange,
                market_type=market_type,
                last=1.0,
                volume_24h=9_000_000,
                updated_at=datetime.now(timezone.utc),
            )
        ]

    manager = MagicMock()
    manager.list_exchanges.return_value = [
        MagicMock(id=ExchangeId.BINANCE, market_types=[MarketType.SPOT]),
        MagicMock(id=ExchangeId.BYBIT, market_types=[MarketType.SPOT]),
    ]
    manager.list_markets = AsyncMock(side_effect=fake_list)
    manager.fetch_tickers_24h = AsyncMock(side_effect=fake_tickers)
    monkeypatch.setattr("app.scanner.universe.get_exchange_manager", lambda: manager)
    cache = MagicMock()
    cache.get.return_value = None
    cache.set = MagicMock()
    monkeypatch.setattr("app.scanner.universe.get_markets_cache", lambda: cache)

    cfg = ScannerConfig(
        default_exchanges=[ExchangeId.BINANCE, ExchangeId.BYBIT],
        default_market_types=[MarketType.SPOT],
    )
    result = await discover_universe(cfg)
    assert any("binance" in e.lower() for e in result.errors)
    assert result.selected_pairs == 1
    assert result.candidates[0].exchange == ExchangeId.BYBIT


@pytest.mark.asyncio
async def test_staged_scan_metrics_and_partial_tf_failure(monkeypatch):
    candidates = [
        ScanCandidate(
            exchange=ExchangeId.BINANCE,
            market_type=MarketType.SPOT,
            symbol="BTC/USDT",
            base="BTC",
            quote_volume_24h=1e9,
        ),
        ScanCandidate(
            exchange=ExchangeId.BYBIT,
            market_type=MarketType.SPOT,
            symbol="ETH/USDT",
            base="ETH",
            quote_volume_24h=5e8,
        ),
    ]

    from app.scanner.universe import UniverseBucketStats

    async def fake_universe2(_config):
        return UniverseDiscoveryResult(
            candidates=candidates,
            discovered_pairs=100,
            eligible_pairs=50,
            selected_pairs=2,
            ranking_method=RANKING_METHOD,
            per_market=[
                UniverseBucketStats(
                    exchange="binance",
                    market_type="spot",
                    discovered=60,
                    eligible=30,
                    selected=1,
                    excluded=29,
                ),
                UniverseBucketStats(
                    exchange="bybit",
                    market_type="spot",
                    discovered=40,
                    eligible=20,
                    selected=1,
                    excluded=19,
                ),
            ],
        )

    async def fake_analyze(cand, *, config, cache, execution_timeframe):
        # Fail one TF for BTC only → pair partial
        if cand.symbol == "BTC/USDT" and execution_timeframe == EXECUTION_TIMEFRAMES[0]:
            raise RuntimeError("rate limit")
        return MarketOpportunity(
            opportunity_id=f"{cand.symbol}:{execution_timeframe.value}",
            exchange=cand.exchange,
            market_type=cand.market_type,
            symbol=cand.symbol,
            base=cand.base,
            timeframe=execution_timeframe,
            status=OpportunityStatus.WAITING,
            decision="WAIT",
            actionable=False,
        )

    monkeypatch.setattr("app.scanner.service.discover_universe", fake_universe2)
    monkeypatch.setattr("app.scanner.service.analyze_candidate", fake_analyze)

    scanner = MarketOpportunityScanner(
        config=ScannerConfig(auto_start=False, max_concurrent_per_exchange=2),
        store=OpportunityStore(),
    )
    summary = await scanner.run_scan(trigger="test")
    assert summary.pairs_discovered == 100
    assert summary.pairs_eligible == 50
    assert summary.pairs_selected == 2
    assert summary.timeframe_analyses_attempted == 8
    assert summary.timeframe_analyses_failed == 1
    assert summary.timeframe_analyses_completed == 7
    assert summary.pairs_scanned == 1  # ETH fully done
    assert summary.pairs_partial == 1  # BTC partial
    assert summary.status == "completed_partial"
    assert summary.duration_seconds is not None
    assert summary.ranking_method == RANKING_METHOD


@pytest.mark.asyncio
async def test_no_overlap_and_concurrency_semaphore(monkeypatch):
    import asyncio

    candidate = ScanCandidate(
        exchange=ExchangeId.BINANCE,
        market_type=MarketType.SPOT,
        symbol="BTC/USDT",
        base="BTC",
    )

    async def fake_universe(_config):
        await asyncio.sleep(0.15)
        return UniverseDiscoveryResult(
            candidates=[candidate],
            discovered_pairs=1,
            eligible_pairs=1,
            selected_pairs=1,
        )

    monkeypatch.setattr("app.scanner.service.discover_universe", fake_universe)
    monkeypatch.setattr(
        "app.scanner.service.analyze_candidate",
        AsyncMock(
            return_value=MarketOpportunity(
                opportunity_id="x",
                exchange=ExchangeId.BINANCE,
                market_type=MarketType.SPOT,
                symbol="BTC/USDT",
                base="BTC",
                timeframe=EXECUTION_TIMEFRAMES[0],
                status=OpportunityStatus.WAITING,
            )
        ),
    )

    scanner = MarketOpportunityScanner(
        config=ScannerConfig(auto_start=False),
        store=OpportunityStore(),
    )

    async def run():
        t1 = asyncio.create_task(scanner.run_scan(trigger="a"))
        await asyncio.sleep(0.05)
        t2 = asyncio.create_task(scanner.run_scan(trigger="b"))
        r1, r2 = await asyncio.gather(t1, t2)
        statuses = {r1.status, r2.status}
        assert "skipped" in statuses

    await run()


def test_default_max_pairs_is_25():
    assert ScannerConfig().max_pairs_per_market == 25
    assert ScannerConfig().scan_interval_seconds == 300.0
