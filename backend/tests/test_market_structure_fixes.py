"""Regression tests for Phase 3.2 audit fixes F3–F5 (+ BOS segments / UTC)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.analysis.market_structure.config import MarketStructureConfig
from app.analysis.market_structure.engine import analyze_market_structure
from app.analysis.market_structure.models import StructureBias, StructureDirection
from app.analysis.market_structure.timestamps import NaiveTimestampError, ensure_utc, format_utc_key
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from tests.test_market_structure_audit import bullish_structure_series, run, C, _bar

CFG = MarketStructureConfig(swing_left=3, swing_right=3)


def test_f4_ensure_utc_rejects_naive() -> None:
    naive = datetime(2024, 1, 1, 12, 0, 0)
    with pytest.raises(NaiveTimestampError):
        ensure_utc(naive)


def test_f4_ensure_utc_normalizes_non_utc() -> None:
    # Fixed offset +02:00 → UTC
    from datetime import timezone as tz

    plus2 = tz(timedelta(hours=2))
    local = datetime(2024, 1, 1, 14, 0, tzinfo=plus2)
    utc = ensure_utc(local)
    assert utc == datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert format_utc_key(local) == "20240101T120000Z"


def test_f4_engine_rejects_naive_candles() -> None:
    naive_ts = datetime(2024, 6, 1, 0, 0, 0)  # naive
    bad = Candle(
        timestamp=naive_ts,
        open=100,
        high=101,
        low=99,
        close=100,
        volume=1,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        is_closed=True,
    )
    with pytest.raises(NaiveTimestampError):
        analyze_market_structure(
            [bad],
            exchange=ExchangeId.BINANCE,
            symbol="BTC/USDT",
            market_type=MarketType.SPOT,
            timeframe=Timeframe.H1,
            config=CFG,
        )


def test_f3_snapshot_aliases_match_unbroken_targets() -> None:
    result = run(bullish_structure_series())
    snap = result.snapshot
    assert snap.active_unbroken_swing_high == snap.active_bullish_level
    assert snap.active_unbroken_swing_low == snap.active_bearish_level


def test_f2_bos_segments_have_start_end() -> None:
    result = run(bullish_structure_series())
    assert result.bos_events
    for bos in result.bos_events:
        assert bos.segment_start is not None
        assert bos.segment_end is not None
        assert bos.segment_start <= bos.segment_end
        assert bos.segment_start == bos.candle_timestamp
        # Chart viz: original swing candle time for swing→break segments
        assert bos.broken_swing_timestamp is not None
        assert bos.broken_swing_timestamp <= bos.candle_timestamp
        swing = next(s for s in result.swings if s.event_key == bos.broken_swing_key)
        assert bos.broken_swing_timestamp == swing.candle_timestamp
        assert bos.broken_level == swing.price
    # Last BOS should be active through series end when no later break
    last = result.bos_events[-1]
    assert last.segment_active is True
    assert last.segment_end == bullish_structure_series()[-1].timestamp
    # Earlier BOS superseded by later BOS
    if len(result.bos_events) >= 2:
        first = result.bos_events[0]
        assert first.segment_active is False
        assert first.segment_end == result.bos_events[1].candle_timestamp


def test_f5_ambiguous_dual_break_no_directional_events() -> None:
    """
    Build SH=130 and SL=100, then one candle that wicks both sides but closes inside.
    """
    base: list[Candle] = []
    base += [_bar(0, 108, 115), _bar(1, 107, 114), _bar(2, 109, 116)]
    base.append(_bar(3, 100, 105, 102))  # SL
    base += [_bar(4, 106, 112), _bar(5, 107, 113), _bar(6, 108, 114)]
    base += [_bar(7, 110, 118), _bar(8, 111, 120), _bar(9, 112, 122)]
    base.append(_bar(10, 124, 130, 128))  # SH
    base += [_bar(11, 118, 125), _bar(12, 117, 124), _bar(13, 116, 123)]
    # Dual wick: high>130, low<100, close inside (100,130)
    dual = C(14, 115, 140, 90, 115)
    assert dual.high > 130 and dual.low < 100
    assert 100 < dual.close < 130

    before = run(base)
    assert before.snapshot.active_unbroken_swing_high == 130
    assert before.snapshot.active_unbroken_swing_low == 100
    bias_before = before.snapshot.bias

    after = run(base + [dual])
    assert after.ambiguous_dual_breaks
    amb = after.ambiguous_dual_breaks[-1]
    assert amb.swing_high_level == 130
    assert amb.swing_low_level == 100
    assert amb.close_price == 115
    assert amb.bias_unchanged == bias_before
    # No new directional break on this candle
    assert not any(e.candle_timestamp == dual.timestamp for e in after.bos_events)
    assert not any(e.candle_timestamp == dual.timestamp for e in after.choch_events)
    assert not any(e.candle_timestamp == dual.timestamp for e in after.mss_events)
    assert after.snapshot.bias == bias_before
    # Levels remain unbroken
    assert after.snapshot.active_unbroken_swing_high == 130
    assert after.snapshot.active_unbroken_swing_low == 100
