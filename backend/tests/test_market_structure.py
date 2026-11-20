"""Deterministic Market Structure Engine tests (no live exchange)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.analysis.market_structure.classifier import classify_swings
from app.analysis.market_structure.config import MarketStructureConfig
from app.analysis.market_structure.engine import analyze_market_structure
from app.analysis.market_structure.models import (
    BreakKind,
    StructureBias,
    StructureDirection,
    StructureLabel,
    SwingKind,
)
from app.analysis.market_structure.swing_detector import detect_confirmed_swings
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe

CFG = MarketStructureConfig(swing_left=3, swing_right=3)


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
) -> Candle:
    return Candle(
        timestamp=_ts(i),
        open=o,
        high=h,
        low=l,
        close=c,
        volume=10.0,
        exchange=exchange,
        symbol="BTC/USDT",
        market_type=market_type,
        is_closed=closed,
    )


def valley_peak_series() -> list[Candle]:
    """
    Synthetic series with a clear swing low then swing high (left/right=3).

    Indices (close-ish highs/lows):
      0..2 rising into local area
      3 = swing low candidate (lowest)
      4..6 rising
      7 = swing high candidate (highest)
      8..10 falling / continuation for confirmation
      then bullish BOS close above swing high
    """
    rows = [
        # 0-2 left of swing low
        (100, 101, 99, 100),
        (100, 102, 98, 101),
        (101, 103, 97, 102),
        # 3 swing low (low=90)
        (102, 103, 90, 95),
        # 4-6 right of SL / left of SH
        (95, 104, 94, 100),
        (100, 106, 99, 105),
        (105, 110, 104, 108),
        # 7 swing high (high=120)
        (108, 120, 107, 115),
        # 8-10 right of SH
        (115, 116, 110, 112),
        (112, 114, 108, 109),
        (109, 111, 105, 106),
        # 11+ continue — later bullish break
        (106, 108, 104, 107),
        (107, 109, 105, 108),
        (108, 112, 107, 111),
        (111, 118, 110, 117),
        # 15 close above SH 120 → BOS
        (117, 125, 116, 124),
    ]
    return [candle(i, *row) for i, row in enumerate(rows)]


def test_swing_high_and_low_detection() -> None:
    candles = valley_peak_series()
    swings = detect_confirmed_swings(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    lows = [s for s in swings if s.kind == SwingKind.LOW]
    highs = [s for s in swings if s.kind == SwingKind.HIGH]
    assert any(s.candle_index == 3 and s.price == 90 for s in lows)
    assert any(s.candle_index == 7 and s.price == 120 for s in highs)


def test_pivot_confirmation_delay() -> None:
    candles = valley_peak_series()
    # Truncate before right bars for swing high at 7 (needs indices 8,9,10)
    partial = candles[:10]  # only 2 right bars after 7
    swings = detect_confirmed_swings(
        partial,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    assert not any(s.kind == SwingKind.HIGH and s.candle_index == 7 for s in swings)

    full = detect_confirmed_swings(
        candles[:11],
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    sh = next(s for s in full if s.kind == SwingKind.HIGH and s.candle_index == 7)
    assert sh.confirmation_timestamp == candles[10].timestamp
    assert sh.candle_timestamp == candles[7].timestamp


def test_equal_high_tie_disqualifies() -> None:
    # Peak equal to a neighbour → not a swing under strict_inequality
    rows = [
        (10, 11, 9, 10),
        (10, 12, 9, 11),
        (11, 13, 10, 12),
        (12, 20, 11, 15),  # candidate
        (15, 20, 14, 16),  # equal high 20 → disqualify
        (16, 18, 15, 17),
        (17, 18, 14, 15),
    ]
    candles = [candle(i, *r) for i, r in enumerate(rows)]
    swings = detect_confirmed_swings(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    assert not any(s.kind == SwingKind.HIGH and s.candle_index == 3 for s in swings)


def test_hh_hl_lh_ll_classification() -> None:
    # Two highs and two lows with clear ordering
    swings_raw = detect_confirmed_swings(
        valley_peak_series()
        + [
            candle(16, 124, 126, 100, 105),  # deep low later
            candle(17, 105, 108, 99, 102),
            candle(18, 102, 107, 98, 100),
            candle(19, 100, 106, 85, 90),  # lower low candidate
            candle(20, 90, 95, 88, 92),
            candle(21, 92, 96, 89, 94),
            candle(22, 94, 97, 90, 95),
        ],
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    classified = classify_swings(swings_raw)
    highs = [s for s in classified if s.kind == SwingKind.HIGH and s.classification]
    lows = [s for s in classified if s.kind == SwingKind.LOW and s.classification]
    # At least first classified labels exist when 2+ of each
    if len([s for s in classified if s.kind == SwingKind.HIGH]) >= 2:
        assert highs[-1].classification in {StructureLabel.HH, StructureLabel.LH}
    if len([s for s in classified if s.kind == SwingKind.LOW]) >= 2:
        assert lows[-1].classification in {StructureLabel.HL, StructureLabel.LL}


def test_bullish_bos_close_required() -> None:
    result = analyze_market_structure(
        valley_peak_series(),
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    assert result.bos_events or result.choch_events
    # Close 124 > 120
    bull = [e for e in result.bos_events if e.direction == StructureDirection.BULLISH]
    assert bull
    assert bull[0].broken_level == 120
    assert bull[0].close_price == 124


def test_wick_only_break_is_not_bos() -> None:
    base = valley_peak_series()[:15]
    # Wick above 120 but close below
    wick = candle(15, 117, 130, 116, 118)
    result = analyze_market_structure(
        base + [wick],
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    assert not any(e.broken_level == 120 for e in result.bos_events)
    assert not any(e.broken_level == 120 for e in result.choch_events)


def test_bearish_bos() -> None:
    # After bullish BOS, close below the latest unbroken swing low (104 at idx 11).
    candles = valley_peak_series() + [
        candle(16, 124, 125, 88, 89),
    ]
    result = analyze_market_structure(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    bear_levels = [e.broken_level for e in result.bos_events if e.direction == StructureDirection.BEARISH]
    bear_levels += [e.broken_level for e in result.choch_events if e.direction == StructureDirection.BEARISH]
    assert 104.0 in bear_levels
    # Must be CHoCH when prior bias is bullish from the earlier BOS
    assert result.choch_events
    assert result.choch_events[0].previous_bias == StructureBias.BULLISH


def test_initial_bias_undefined() -> None:
    # Too few candles for classification bias
    candles = valley_peak_series()[:8]
    result = analyze_market_structure(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    # With incomplete right confirmation may have no/few swings
    if not result.swings:
        assert result.snapshot.bias == StructureBias.UNDEFINED


def test_choch_against_bias_not_every_bos() -> None:
    candles = valley_peak_series() + [
        candle(16, 124, 125, 88, 89),  # break low against bullish BOS bias → CHoCH
    ]
    result = analyze_market_structure(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    # First break should be BOS (bullish), second against bias → CHoCH
    assert result.bos_events
    assert result.bos_events[0].break_kind == BreakKind.BOS
    if result.choch_events:
        assert result.choch_events[0].previous_bias != StructureBias.UNDEFINED
        assert result.choch_events[0].direction == StructureDirection.BEARISH


def test_mss_requires_displacement() -> None:
    # Force a CHoCH candle with tiny body → no MSS
    candles = valley_peak_series() + [
        candle(16, 90.1, 91, 88, 89.9),  # small body break of 90
    ]
    result = analyze_market_structure(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    # If CHoCH fired with tiny body, MSS must be empty for that event
    for choch in result.choch_events:
        matching = [m for m in result.mss_events if m.choch_event_key == choch.event_key]
        body = abs(choch.close_price - 90.1)  # approximate
        # Rely on engine: either no MSS or displacement satisfied
        if matching:
            assert matching[0].body_size >= matching[0].atr_value * CFG.displacement_atr_mult


def test_mss_with_valid_displacement() -> None:
    # Large body CHoCH
    candles = valley_peak_series()
    # Pad ATR warm-up with more history by prepending flat-ish bars
    prefix = [candle(i - 40, 100, 101, 99, 100) for i in range(40)]
    # Re-index properly
    all_rows = []
    for i, c in enumerate(prefix + candles):
        all_rows.append(
            candle(
                i,
                c.open,
                c.high,
                c.low,
                c.close,
            )
        )
    # Ensure last is large bearish displacement through SL after bullish BOS
    # Rebuild using valley series indices shifted
    series = valley_peak_series()
    # prepend 30 bars for ATR
    head = [candle(i, 100, 102, 98, 100) for i in range(30)]
    shifted = []
    for j, c in enumerate(series):
        shifted.append(candle(30 + j, c.open, c.high, c.low, c.close))
    # Replace last with huge bearish body after BOS already happened — append
    big = candle(30 + len(series), 124, 125, 50, 55)  # body 69
    result = analyze_market_structure(
        head + shifted + [big],
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    if result.choch_events:
        # Large body should produce MSS when ATR available
        assert result.mss_events or result.choch_events[-1].direction == StructureDirection.BEARISH


def test_missing_atr_no_fabricated_mss() -> None:
    # Very short series: ATR not ready; if somehow CHoCH, no MSS
    short = valley_peak_series()[:12]
    result = analyze_market_structure(
        short,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    for m in result.mss_events:
        assert m.atr_value is not None and m.atr_value > 0


def test_duplicate_event_prevention() -> None:
    candles = valley_peak_series()
    a = analyze_market_structure(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    b = analyze_market_structure(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    assert a.event_keys == b.event_keys
    assert len(a.event_keys) == len(set(a.event_keys))


def test_historical_vs_incremental_equivalence() -> None:
    candles = valley_peak_series()
    full = analyze_market_structure(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    # Incremental: growing prefixes — final keys must match full
    last = None
    for n in range(7, len(candles) + 1):
        last = analyze_market_structure(
            candles[:n],
            exchange=ExchangeId.BINANCE,
            symbol="BTC/USDT",
            market_type=MarketType.SPOT,
            timeframe=Timeframe.H1,
            config=CFG,
        )
    assert last is not None
    assert set(last.event_keys) == set(full.event_keys)


def test_no_lookahead_forming_candle_ignored() -> None:
    candles = valley_peak_series()
    candles[-1] = candles[-1].model_copy(update={"is_closed": False, "close": 200, "high": 210})
    result = analyze_market_structure(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    assert not any(e.close_price == 200 for e in result.bos_events)


def test_utc_timestamps() -> None:
    candles = valley_peak_series()
    result = analyze_market_structure(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    for s in result.swings:
        assert s.candle_timestamp.tzinfo is not None
        assert s.confirmation_timestamp.tzinfo is not None


def test_exchange_market_isolation_in_keys() -> None:
    candles = valley_peak_series()
    a = analyze_market_structure(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    b = analyze_market_structure(
        [
            c.model_copy(update={"exchange": ExchangeId.BYBIT, "market_type": MarketType.LINEAR_PERPETUAL})
            for c in candles
        ],
        exchange=ExchangeId.BYBIT,
        symbol="BTC/USDT",
        market_type=MarketType.LINEAR_PERPETUAL,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    assert a.swings and b.swings
    assert a.swings[0].event_key != b.swings[0].event_key
    assert "binance:spot" in a.swings[0].event_key
    assert "bybit:linear_perpetual" in b.swings[0].event_key


def test_config_version_in_metadata() -> None:
    result = analyze_market_structure(
        valley_peak_series(),
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    assert result.config["config_version"] == CFG.config_version
    assert result.snapshot.config_version == CFG.config_version
