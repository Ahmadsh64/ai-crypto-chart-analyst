"""Phase 3.3.1 — diameter clustering, reaction_hint, REST/WS window consistency."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.analysis.liquidity.config import (
    DEFAULT_LIQUIDITY_CONFIG,
    LIQUIDITY_ANALYSIS_CANDLE_LIMIT,
    LiquidityConfig,
)
from app.analysis.liquidity.eq_cluster import cluster_equal_extremes
from app.analysis.liquidity.engine import analyze_liquidity
from app.analysis.liquidity.models import LiquidityType, ReactionHint
from app.analysis.market_structure.models import SwingKind, SwingPoint
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.market_data.liquidity_runtime import LiquidityRuntime
from tests.test_liquidity import base_series, candle, swing


DIAM_CFG = LiquidityConfig(
    atr_tolerance_mult=0.15,
    fallback_tolerance_pct=0.001,
    eq_cluster_min_swings=2,
    config_version="liq-v1.1.0-balanced",
)


def _ts(i: int) -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc) + timedelta(hours=i)


def _sh(price: float, idx: int, confirm_idx: int, key_suffix: str) -> SwingPoint:
    return SwingPoint(
        event_key=(
            f"swing:high:binance:spot:BTC/USDT:1h:"
            f"{_ts(idx).strftime('%Y%m%dT%H%M%SZ')}:{key_suffix}"
        ),
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        kind=SwingKind.HIGH,
        price=price,
        candle_timestamp=_ts(idx),
        confirmation_timestamp=_ts(confirm_idx),
        confirmed=True,
        classification=None,
        config_version="ms-v1.0.0-balanced",
        candle_index=idx,
    )


def _cluster_abc(t: float = 0.15):
    """A=100, B=100.14, C=100.28 with ATR=1 → T = atr_tolerance_mult * 1."""
    cfg = LiquidityConfig(
        atr_tolerance_mult=t,
        fallback_tolerance_pct=0.001,
        eq_cluster_min_swings=2,
    )
    swings = [
        _sh(100.00, 5, 8, "a"),
        _sh(100.14, 15, 18, "b"),
        _sh(100.28, 25, 28, "c"),
    ]
    atr = [1.0] * 40
    idx_map = {_ts(i): i for i in range(40)}
    return cluster_equal_extremes(
        swings,
        kind=SwingKind.HIGH,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        atr_by_index=atr,
        index_by_confirm_ts=idx_map,
        cfg=cfg,
    ), cfg, swings


def test_331_A_three_swings_do_not_form_one_wide_cluster() -> None:
    clusters, _, _ = _cluster_abc(0.15)
    # A–B diameter 0.14 ≤ 0.15; A–C / full set 0.28 > 0.15 → not one triple cluster
    assert all(c.member_count < 3 for c in clusters)
    assert not any(c.member_count == 3 for c in clusters)
    # Expect A+B as one EQH (2 members); C alone insufficient
    assert len(clusters) == 1
    prices = sorted(m.price for m in clusters[0].members)
    assert prices == [100.00, 100.14]


def test_331_B_every_cluster_diameter_le_tolerance() -> None:
    clusters, _, _ = _cluster_abc(0.15)
    for c in clusters:
        assert c.price_range <= c.tolerance_used + 1e-12
        assert c.max_price - c.min_price == c.price_range


def test_331_C_exact_boundary_diameter_accepted() -> None:
    # A=100, B=100.15 → diameter == T=0.15 exactly
    cfg = LiquidityConfig(atr_tolerance_mult=0.15, eq_cluster_min_swings=2)
    swings = [_sh(100.00, 5, 8, "a"), _sh(100.15, 15, 18, "b")]
    atr = [1.0] * 40
    idx_map = {_ts(i): i for i in range(40)}
    clusters = cluster_equal_extremes(
        swings,
        kind=SwingKind.HIGH,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        atr_by_index=atr,
        index_by_confirm_ts=idx_map,
        cfg=cfg,
    )
    assert len(clusters) == 1
    assert abs(clusters[0].price_range - 0.15) < 1e-12
    assert clusters[0].price_range <= clusters[0].tolerance_used + 1e-12


def test_331_D_repeated_calculation_identical_membership_and_ids() -> None:
    a, _, _ = _cluster_abc(0.15)
    b, _, _ = _cluster_abc(0.15)
    assert [c.event_key for c in a] == [c.event_key for c in b]
    assert [[m.swing_key for m in c.members] for c in a] == [
        [m.swing_key for m in c.members] for c in b
    ]
    assert [c.representative_level for c in a] == [c.representative_level for c in b]


def test_331_E_new_swing_no_duplicate_membership() -> None:
    cfg = LiquidityConfig(atr_tolerance_mult=0.15, eq_cluster_min_swings=2)
    atr = [1.0] * 50
    idx_map = {_ts(i): i for i in range(50)}
    base = [_sh(100.00, 5, 8, "a"), _sh(100.10, 15, 18, "b")]
    with_new = base + [_sh(100.12, 25, 28, "d")]  # fits diameter with A+B
    clusters = cluster_equal_extremes(
        with_new,
        kind=SwingKind.HIGH,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        atr_by_index=atr,
        index_by_confirm_ts=idx_map,
        cfg=cfg,
    )
    keys = [m.swing_key for c in clusters for m in c.members]
    assert len(keys) == len(set(keys))
    assert clusters[0].member_count == 3
    assert clusters[0].level == clusters[0].representative_level


def test_331_F_unconfirmed_future_swing_excluded() -> None:
    cfg = LiquidityConfig(atr_tolerance_mult=0.15, eq_cluster_min_swings=2)
    atr = [1.0] * 50
    idx_map = {_ts(i): i for i in range(50)}
    confirmed = [_sh(100.00, 5, 8, "a"), _sh(100.10, 15, 18, "b")]
    future = _sh(100.05, 35, 38, "future")
    # as_of before future confirmation
    clusters = cluster_equal_extremes(
        confirmed + [future],
        kind=SwingKind.HIGH,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        atr_by_index=atr,
        index_by_confirm_ts=idx_map,
        cfg=cfg,
        as_of=_ts(20),
    )
    assert len(clusters) == 1
    assert all(m.confirmation_timestamp <= _ts(20) for m in clusters[0].members)
    assert future.event_key not in {m.swing_key for m in clusters[0].members}

    unconfirmed = SwingPoint(
        event_key="swing:high:unconfirmed",
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        kind=SwingKind.HIGH,
        price=100.05,
        candle_timestamp=_ts(10),
        confirmation_timestamp=_ts(13),
        confirmed=False,
        classification=None,
        config_version="ms-v1.0.0-balanced",
        candle_index=10,
    )
    clusters2 = cluster_equal_extremes(
        confirmed + [unconfirmed],
        kind=SwingKind.HIGH,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        atr_by_index=atr,
        index_by_confirm_ts=idx_map,
        cfg=cfg,
    )
    assert unconfirmed.event_key not in {
        m.swing_key for c in clusters2 for m in c.members
    }


def test_331_reaction_hint_bsl_bearish_ssl_bullish() -> None:
    candles = base_series(25)
    candles[12] = candle(12, 119, 122, 118, 119)
    swings = [swing(kind=SwingKind.HIGH, price=120.0, idx=5, confirm_idx=8)]
    result = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=DIAM_CFG,
        swings=swings,
    )
    assert result.sweeps[0].liquidity_type == LiquidityType.BSL
    assert result.sweeps[0].reaction_hint == ReactionHint.BEARISH

    candles2 = base_series(25)
    candles2[12] = candle(12, 81, 82, 78, 81)
    swings2 = [swing(kind=SwingKind.LOW, price=80.0, idx=5, confirm_idx=8)]
    result2 = analyze_liquidity(
        candles2,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=DIAM_CFG,
        swings=swings2,
    )
    assert result2.sweeps[0].liquidity_type == LiquidityType.SSL
    assert result2.sweeps[0].reaction_hint == ReactionHint.BULLISH


def test_331_cluster_exposes_price_range_fields() -> None:
    clusters, _, _ = _cluster_abc(0.15)
    c = clusters[0]
    assert c.min_price == 100.00
    assert c.max_price == 100.14
    assert abs(c.price_range - 0.14) < 1e-12
    assert c.representative_level == c.level
    assert c.member_count == 2


def test_331_rest_ws_canonical_window_constant() -> None:
    assert LIQUIDITY_ANALYSIS_CANDLE_LIMIT == 500
    assert DEFAULT_LIQUIDITY_CONFIG.analysis_candle_limit == 500
    runtime = LiquidityRuntime()
    assert runtime._max_candles == LIQUIDITY_ANALYSIS_CANDLE_LIMIT


def test_331_config_version_bumped() -> None:
    assert DEFAULT_LIQUIDITY_CONFIG.config_version == "liq-v1.1.0-balanced"
    candles = [candle(i, 100, 101, 99, 100) for i in range(20)]
    result = analyze_liquidity(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        swings=[],
    )
    assert result.snapshot.config_version == "liq-v1.1.0-balanced"
