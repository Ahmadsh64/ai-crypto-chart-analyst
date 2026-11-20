"""Deterministic Liquidity Engine tests A–Q (Phase 3.3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.analysis.liquidity import analyze_liquidity
from app.analysis.liquidity.config import LiquidityConfig
from app.analysis.liquidity.engine import new_liquidity_events_since
from app.analysis.liquidity.models import (
    LiquiditySourceType,
    LiquidityStatus,
    LiquidityType,
    ReactionHint,
    SweepDirection,
)
from app.analysis.market_structure.models import SwingKind, SwingPoint
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.main import app

CFG = LiquidityConfig(
    atr_tolerance_mult=0.5,  # generous for synthetic ATR-less / small ranges
    fallback_tolerance_pct=0.01,  # 1% — easy EQH/EQL in fixtures
    min_penetration_atr_mult=0.01,
    min_penetration_fallback_pct=0.0001,
    eq_cluster_min_swings=2,
)


def _ts(i: int) -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc) + timedelta(hours=i)


def candle(
    i: int,
    o: float,
    h: float,
    l: float,
    c: float,
    *,
    closed: bool = True,
    exchange: ExchangeId = ExchangeId.BINANCE,
    market_type: MarketType = MarketType.SPOT,
    symbol: str = "BTC/USDT",
) -> Candle:
    return Candle(
        timestamp=_ts(i),
        open=o,
        high=h,
        low=l,
        close=c,
        volume=10.0,
        exchange=exchange,
        symbol=symbol,
        market_type=market_type,
        is_closed=closed,
    )


def swing(
    *,
    kind: SwingKind,
    price: float,
    idx: int,
    confirm_idx: int | None = None,
    exchange: ExchangeId = ExchangeId.BINANCE,
    market_type: MarketType = MarketType.SPOT,
    symbol: str = "BTC/USDT",
    timeframe: Timeframe = Timeframe.H1,
) -> SwingPoint:
    conf_i = confirm_idx if confirm_idx is not None else idx + 3
    key = (
        f"swing:{kind.value}:{exchange.value}:{market_type.value}:{symbol}:"
        f"{timeframe.value}:{_ts(idx).strftime('%Y%m%dT%H%M%SZ')}"
    )
    return SwingPoint(
        event_key=key,
        exchange=exchange,
        symbol=symbol,
        market_type=market_type,
        timeframe=timeframe,
        kind=kind,
        price=price,
        candle_timestamp=_ts(idx),
        confirmation_timestamp=_ts(conf_i),
        confirmed=True,
        classification=None,
        config_version="ms-v1.0.0-balanced",
        candle_index=idx,
    )


def base_series(n: int = 40) -> list[Candle]:
    """Flat-ish closed candles for sweep injection."""
    out: list[Candle] = []
    for i in range(n):
        mid = 100.0
        out.append(candle(i, mid, mid + 1, mid - 1, mid))
    return out


def test_A_eqh_two_swing_highs_within_tolerance() -> None:
    candles = base_series()
    swings = [
        swing(kind=SwingKind.HIGH, price=120.0, idx=5, confirm_idx=8),
        swing(kind=SwingKind.HIGH, price=120.5, idx=15, confirm_idx=18),
    ]
    result = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        swings=swings,
    )
    assert len(result.eqh_clusters) == 1
    assert result.eqh_clusters[0].member_count == 2
    assert abs(result.eqh_clusters[0].level - 120.25) < 1e-9


def test_B_eql_two_swing_lows_within_tolerance() -> None:
    candles = base_series()
    swings = [
        swing(kind=SwingKind.LOW, price=80.0, idx=5, confirm_idx=8),
        swing(kind=SwingKind.LOW, price=80.4, idx=15, confirm_idx=18),
    ]
    result = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        swings=swings,
    )
    assert len(result.eql_clusters) == 1
    assert result.eql_clusters[0].kind == "eql"


def test_C_swing_high_is_bsl() -> None:
    candles = base_series()
    swings = [swing(kind=SwingKind.HIGH, price=130.0, idx=5, confirm_idx=8)]
    result = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        swings=swings,
    )
    assert len(result.bsl_levels) == 1
    assert result.bsl_levels[0].liquidity_type == LiquidityType.BSL
    assert result.bsl_levels[0].source_type == LiquiditySourceType.SWING
    assert result.bsl_levels[0].price == 130.0


def test_D_swing_low_is_ssl() -> None:
    candles = base_series()
    swings = [swing(kind=SwingKind.LOW, price=70.0, idx=5, confirm_idx=8)]
    result = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        swings=swings,
    )
    assert len(result.ssl_levels) == 1
    assert result.ssl_levels[0].liquidity_type == LiquidityType.SSL


def test_E_bullish_side_sweep_of_bsl() -> None:
    candles = base_series(25)
    # After confirmation at 8, sweep at index 12: wick above 120, close below
    candles[12] = candle(12, 119, 122, 118, 119)
    swings = [swing(kind=SwingKind.HIGH, price=120.0, idx=5, confirm_idx=8)]
    result = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        swings=swings,
    )
    assert len(result.sweeps) == 1
    assert result.sweeps[0].liquidity_type == LiquidityType.BSL
    assert result.sweeps[0].reaction_hint == ReactionHint.BEARISH
    assert result.sweeps[0].direction == SweepDirection.BULLISH_SIDE  # deprecated BC
    assert result.sweeps[0].confirmed is True
    assert result.bsl_levels[0].status == LiquidityStatus.SWEPT


def test_F_bearish_side_sweep_of_ssl() -> None:
    candles = base_series(25)
    candles[12] = candle(12, 81, 82, 78, 81)
    swings = [swing(kind=SwingKind.LOW, price=80.0, idx=5, confirm_idx=8)]
    result = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        swings=swings,
    )
    assert len(result.sweeps) == 1
    assert result.sweeps[0].liquidity_type == LiquidityType.SSL
    assert result.sweeps[0].reaction_hint == ReactionHint.BULLISH
    assert result.sweeps[0].direction == SweepDirection.BEARISH_SIDE  # deprecated BC
    assert result.ssl_levels[0].status == LiquidityStatus.SWEPT


def test_G_close_above_bsl_is_broken_not_sweep() -> None:
    candles = base_series(25)
    candles[12] = candle(12, 119, 125, 118, 124)  # closes above 120
    swings = [swing(kind=SwingKind.HIGH, price=120.0, idx=5, confirm_idx=8)]
    result = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        swings=swings,
    )
    assert result.sweeps == []
    assert result.bsl_levels[0].status == LiquidityStatus.BROKEN


def test_H_close_below_ssl_is_broken_not_sweep() -> None:
    candles = base_series(25)
    candles[12] = candle(12, 81, 82, 75, 76)
    swings = [swing(kind=SwingKind.LOW, price=80.0, idx=5, confirm_idx=8)]
    result = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        swings=swings,
    )
    assert result.sweeps == []
    assert result.ssl_levels[0].status == LiquidityStatus.BROKEN


def test_I_insufficient_swings_no_eq_cluster() -> None:
    candles = base_series()
    swings = [swing(kind=SwingKind.HIGH, price=120.0, idx=5, confirm_idx=8)]
    result = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        swings=swings,
    )
    assert result.eqh_clusters == []


def test_J_outside_tolerance_no_eqh() -> None:
    tight = LiquidityConfig(fallback_tolerance_pct=0.00001, atr_tolerance_mult=0.00001)
    candles = base_series()
    swings = [
        swing(kind=SwingKind.HIGH, price=120.0, idx=5, confirm_idx=8),
        swing(kind=SwingKind.HIGH, price=130.0, idx=15, confirm_idx=18),
    ]
    result = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=tight,
        swings=swings,
    )
    assert result.eqh_clusters == []
    # Still two individual BSL levels
    assert len(result.bsl_levels) == 2


def test_K_forming_candle_no_confirmed_sweep() -> None:
    candles = base_series(20)
    candles.append(candle(20, 119, 122, 118, 119, closed=False))
    swings = [swing(kind=SwingKind.HIGH, price=120.0, idx=5, confirm_idx=8)]
    result = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        swings=swings,
        include_unconfirmed=False,
    )
    assert result.sweeps == []
    assert result.bsl_levels[0].status == LiquidityStatus.ACTIVE

    with_prov = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        swings=swings,
        include_unconfirmed=True,
    )
    assert with_prov.sweeps == []
    assert len(with_prov.provisional_sweeps) == 1
    assert with_prov.provisional_sweeps[0].confirmed is False
    assert with_prov.bsl_levels[0].status == LiquidityStatus.ACTIVE


def test_L_ambiguous_dual_cross() -> None:
    candles = base_series(25)
    candles[12] = candle(12, 100, 122, 78, 100)  # wick both sides, close mid
    swings = [
        swing(kind=SwingKind.HIGH, price=120.0, idx=5, confirm_idx=8),
        swing(kind=SwingKind.LOW, price=80.0, idx=6, confirm_idx=9),
    ]
    result = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        swings=swings,
    )
    assert result.sweeps == []
    assert len(result.ambiguous_crosses) == 1
    assert result.bsl_levels[0].status == LiquidityStatus.ACTIVE
    assert result.ssl_levels[0].status == LiquidityStatus.ACTIVE


def test_M_duplicate_prevention_and_reconnect_diff() -> None:
    candles = base_series(25)
    candles[12] = candle(12, 119, 122, 118, 119)
    swings = [swing(kind=SwingKind.HIGH, price=120.0, idx=5, confirm_idx=8)]
    a = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        swings=swings,
    )
    b = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        swings=swings,
    )
    assert [s.event_key for s in a.sweeps] == [s.event_key for s in b.sweeps]
    assert len(a.sweeps) == 1
    fresh = new_liquidity_events_since(b, set(a.event_keys))
    assert fresh["sweeps"] == []
    assert fresh["bsl_levels"] == []


def test_N_historical_vs_incremental_prefix_equivalence() -> None:
    candles = base_series(30)
    candles[12] = candle(12, 119, 122, 118, 119)
    swings = [swing(kind=SwingKind.HIGH, price=120.0, idx=5, confirm_idx=8)]
    full = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        swings=swings,
    )
    # Prefix through sweep bar
    prefix = analyze_liquidity(
        candles[:13],
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        swings=swings,
    )
    assert [s.event_key for s in prefix.sweeps] == [s.event_key for s in full.sweeps]
    assert prefix.sweeps[0].level_price == full.sweeps[0].level_price


def test_O_no_lookahead_before_confirmation() -> None:
    candles = base_series(20)
    # Sweep candle BEFORE swing confirmation (confirm at 15, sweep at 10)
    candles[10] = candle(10, 119, 122, 118, 119)
    swings = [swing(kind=SwingKind.HIGH, price=120.0, idx=5, confirm_idx=15)]
    result = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        swings=swings,
    )
    assert result.sweeps == []
    assert result.bsl_levels[0].status == LiquidityStatus.ACTIVE


def test_P_exchange_market_isolation_in_keys() -> None:
    candles = base_series()
    swings_a = [swing(kind=SwingKind.HIGH, price=120.0, idx=5, confirm_idx=8)]
    swings_b = [
        swing(
            kind=SwingKind.HIGH,
            price=120.0,
            idx=5,
            confirm_idx=8,
            exchange=ExchangeId.BYBIT,
            market_type=MarketType.LINEAR_PERPETUAL,
        )
    ]
    a = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        swings=swings_a,
    )
    b_candles = [
        candle(
            i,
            100,
            101,
            99,
            100,
            exchange=ExchangeId.BYBIT,
            market_type=MarketType.LINEAR_PERPETUAL,
        )
        for i in range(40)
    ]
    b = analyze_liquidity(
        b_candles,
        exchange=ExchangeId.BYBIT,
        symbol="BTC/USDT",
        market_type=MarketType.LINEAR_PERPETUAL,
        timeframe=Timeframe.H1,
        config=CFG,
        swings=swings_b,
    )
    assert a.bsl_levels[0].event_key != b.bsl_levels[0].event_key
    assert "binance" in a.bsl_levels[0].event_key
    assert "bybit" in b.bsl_levels[0].event_key


def test_Q_utc_timestamps() -> None:
    candles = base_series(25)
    candles[12] = candle(12, 119, 122, 118, 119)
    swings = [swing(kind=SwingKind.HIGH, price=120.0, idx=5, confirm_idx=8)]
    result = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        swings=swings,
    )
    for s in result.sweeps:
        assert s.candle_timestamp.tzinfo is not None
        assert s.confirmation_timestamp.tzinfo is not None
    for lv in result.bsl_levels:
        assert lv.detection_timestamp.tzinfo is not None


def test_api_liquidity_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    candles = base_series(30)
    swings = [
        swing(kind=SwingKind.HIGH, price=120.0, idx=5, confirm_idx=8),
        swing(kind=SwingKind.HIGH, price=120.3, idx=15, confirm_idx=18),
    ]

    async def _fake_fetch(*_a, **_k):
        return candles

    from app.exchanges import manager as exch_mgr
    from app.analysis import liquidity as liq_pkg
    from app.services import liquidity_service as svc

    monkeypatch.setattr(
        exch_mgr.get_exchange_manager(),
        "fetch_ohlcv",
        _fake_fetch,
    )

    # Inject swings via wrapping analyze
    real = liq_pkg.analyze_liquidity

    def _wrapped(cands, **kwargs):
        kwargs["swings"] = swings
        kwargs["config"] = CFG
        return real(cands, **kwargs)

    monkeypatch.setattr(svc, "analyze_liquidity", _wrapped)

    client = TestClient(app)
    res = client.get(
        "/api/v1/liquidity",
        params={
            "exchange": "binance",
            "market_type": "spot",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "limit": 100,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert "eqh_clusters" in body
    assert "bsl_levels" in body
    assert "ssl_levels" in body
    assert "sweeps" in body
    assert body["config"]["config_version"] == "liq-v1.1.0-balanced"
    assert body["snapshot"]["sweep_count"] == len(body["sweeps"])
    assert "candle_window" in body["metadata"]
    assert "confidence" not in body
