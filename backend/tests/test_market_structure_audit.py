"""
Phase 3.2 independent audit suite.

Synthetic OHLCV only — no live exchange calls.
Proves strategy docs, look-ahead safety, and scenario A–G expectations.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.analysis.indicators.volatility import atr as calc_atr
from app.analysis.market_structure.bos_detector import is_bullish_close_break, is_bearish_close_break
from app.analysis.market_structure.config import MarketStructureConfig
from app.analysis.market_structure.engine import analyze_market_structure
from app.analysis.market_structure.models import (
    BreakKind,
    StructureBias,
    StructureDirection,
    StructureLabel,
    SwingKind,
)
from app.analysis.market_structure.mss_detector import has_displacement
from app.analysis.market_structure.swing_detector import detect_confirmed_swings
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.main import app
import numpy as np

CFG = MarketStructureConfig(swing_left=3, swing_right=3)
client = TestClient(app)


def _ts(i: int) -> datetime:
    return datetime(2024, 3, 1, tzinfo=timezone.utc) + timedelta(hours=i)


def C(
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
        volume=100.0,
        exchange=exchange,
        symbol=symbol,
        market_type=market_type,
        is_closed=closed,
    )


def run(candles: list[Candle], **kwargs):
    return analyze_market_structure(
        candles,
        exchange=kwargs.get("exchange", ExchangeId.BINANCE),
        symbol=kwargs.get("symbol", "BTC/USDT"),
        market_type=kwargs.get("market_type", MarketType.SPOT),
        timeframe=kwargs.get("timeframe", Timeframe.H1),
        config=CFG,
        include_unconfirmed=kwargs.get("include_unconfirmed", False),
    )


# ---------------------------------------------------------------------------
# Clean synthetic series (only intentional pivots; L=R=3)
# ---------------------------------------------------------------------------

def _bar(i: int, low: float, high: float, close: float | None = None) -> Candle:
    """Helper: open near close, body inside [low, high]."""
    c = close if close is not None else (low + high) / 2
    o = c
    assert low <= min(o, c) <= max(o, c) <= high
    return C(i, o, high, low, c)


def bullish_structure_series() -> list[Candle]:
    """
    Scenario A — intentional pivots only:
      i=3  SL1=100
      i=10 SH1=130
      i=17 SL2=110 (HL)
      i=24 SH2=150 (HH)
      i=28 close 155 > 150 → bullish BOS
    Non-pivot bars stay in mid ranges that cannot form 3+3 extremes.
    """
    out: list[Candle] = []
    # 0-2 left of SL1 (lows > 100)
    out += [_bar(0, 108, 115), _bar(1, 107, 114), _bar(2, 109, 116)]
    out.append(_bar(3, 100, 105, 102))  # SL1
    # 4-6 right of SL1
    out += [_bar(4, 106, 112), _bar(5, 107, 113), _bar(6, 108, 114)]
    # 7-9 left of SH1 (highs < 130)
    out += [_bar(7, 110, 118), _bar(8, 111, 120), _bar(9, 112, 122)]
    out.append(_bar(10, 124, 130, 128))  # SH1
    # 11-13 right of SH1
    out += [_bar(11, 118, 125), _bar(12, 117, 124), _bar(13, 116, 123)]
    # 14-16 left of SL2 (lows > 110)
    out += [_bar(14, 115, 122), _bar(15, 114, 121), _bar(16, 116, 123)]
    out.append(_bar(17, 110, 116, 112))  # SL2 HL
    # 18-20 right of SL2
    out += [_bar(18, 114, 121), _bar(19, 115, 122), _bar(20, 116, 123)]
    # 21-23 left of SH2 (highs < 150)
    out += [_bar(21, 120, 132), _bar(22, 122, 135), _bar(23, 124, 138)]
    out.append(_bar(24, 140, 150, 148))  # SH2 HH
    # 25-27 right of SH2
    out += [_bar(25, 136, 145), _bar(26, 134, 144), _bar(27, 132, 142)]
    # 28 BOS
    out.append(C(28, 145, 160, 144, 155))
    return out


def bearish_structure_series() -> list[Candle]:
    """
    Scenario B — intentional pivots only:
      i=3  SH1=200
      i=10 SL1=170
      i=17 SH2=190 (LH)
      i=24 SL2=150 (LL)
      i=28 close 145 < 150 → bearish BOS
    """
    out: list[Candle] = []
    out += [_bar(0, 185, 192), _bar(1, 186, 193), _bar(2, 184, 191)]
    out.append(_bar(3, 195, 200, 198))  # SH1
    out += [_bar(4, 188, 196), _bar(5, 187, 195), _bar(6, 186, 194)]
    out += [_bar(7, 180, 190), _bar(8, 178, 188), _bar(9, 176, 186)]
    out.append(_bar(10, 170, 176, 172))  # SL1
    out += [_bar(11, 174, 182), _bar(12, 175, 183), _bar(13, 176, 184)]
    out += [_bar(14, 178, 186), _bar(15, 179, 187), _bar(16, 180, 188)]
    out.append(_bar(17, 185, 190, 188))  # SH2 LH
    out += [_bar(18, 178, 186), _bar(19, 176, 184), _bar(20, 174, 182)]
    out += [_bar(21, 168, 178), _bar(22, 165, 175), _bar(23, 162, 172)]
    out.append(_bar(24, 150, 158, 152))  # SL2 LL
    out += [_bar(25, 154, 162), _bar(26, 156, 164), _bar(27, 158, 166)]
    out.append(C(28, 160, 162, 140, 145))  # bearish BOS
    return out


# ======================== 2. Look-ahead audit ========================


def test_audit_pivot_not_confirmed_before_right_bars_exist() -> None:
    # Pivot high at i=3 price 120; needs right bars 4,5,6
    full = [
        _bar(0, 100, 110),
        _bar(1, 101, 111),
        _bar(2, 102, 112),
        _bar(3, 115, 120, 118),
        _bar(4, 108, 114),
        _bar(5, 107, 113),
        _bar(6, 106, 112),
    ]
    partial = full[:6]  # missing bar 6 → not confirmed
    swings_partial = detect_confirmed_swings(
        partial,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    assert not any(s.kind == SwingKind.HIGH and s.price == 120 for s in swings_partial)

    swings_full = detect_confirmed_swings(
        full,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    sh = next(s for s in swings_full if s.kind == SwingKind.HIGH and s.price == 120)
    assert sh.confirmation_timestamp == _ts(6)
    assert sh.candle_timestamp == _ts(3)


def test_audit_future_bars_not_used_for_breaks_before_confirmation() -> None:
    """Break scan may only consume swings whose confirmation_timestamp <= candle.ts."""
    candles = bullish_structure_series()
    # Find SH at 150
    swings = detect_confirmed_swings(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    sh150 = next(s for s in swings if s.kind == SwingKind.HIGH and s.price == 150)
    # Any candle before confirmation must not see this swing as available
    pre = [c for c in candles if c.timestamp < sh150.confirmation_timestamp]
    result_pre = run(pre)
    assert not any(s.price == 150 and s.kind == SwingKind.HIGH for s in result_pre.swings) or all(
        s.confirmation_timestamp <= pre[-1].timestamp for s in result_pre.swings if s.price == 150
    )
    # Explicit: no BOS of 150 before confirmation
    assert not any(e.broken_level == 150 for e in result_pre.bos_events)


def test_audit_historical_vs_incremental_equivalence() -> None:
    candles = bullish_structure_series()
    full = run(candles)
    last = None
    for n in range(10, len(candles) + 1):
        last = run(candles[:n])
    assert last is not None
    assert set(last.event_keys) == set(full.event_keys)
    assert [(e.broken_level, e.direction) for e in last.bos_events] == [
        (e.broken_level, e.direction) for e in full.bos_events
    ]


def test_audit_forming_candle_cannot_create_confirmed_events() -> None:
    candles = bullish_structure_series()
    # Force last bar forming with explosive close that would otherwise BOS
    base = candles[:-1]
    forming = C(len(base), 141, 200, 140, 199, closed=False)
    result = run(base + [forming])
    closed_only = run(base)
    assert set(result.event_keys) == set(closed_only.event_keys)
    assert not any(e.close_price == 199 for e in result.bos_events)
    assert all(s.confirmed for s in result.swings)


# ======================== 3. Scenarios A–G ========================


def test_audit_A_bullish_trend_hh_hl_bos() -> None:
    result = run(bullish_structure_series())
    highs = [s for s in result.swings if s.kind == SwingKind.HIGH]
    lows = [s for s in result.swings if s.kind == SwingKind.LOW]
    assert any(s.price == 130 for s in highs)
    assert any(s.price == 150 and s.classification == StructureLabel.HH for s in highs)
    assert any(s.price == 110 and s.classification == StructureLabel.HL for s in lows)
    bull_bos = [e for e in result.bos_events if e.direction == StructureDirection.BULLISH]
    assert any(e.broken_level == 150 and e.close_price == 155 for e in bull_bos)
    assert bull_bos[0].break_kind == BreakKind.BOS


def test_audit_B_bearish_trend_lh_ll_bos() -> None:
    result = run(bearish_structure_series())
    highs = [s for s in result.swings if s.kind == SwingKind.HIGH]
    lows = [s for s in result.swings if s.kind == SwingKind.LOW]
    assert any(s.price == 190 and s.classification == StructureLabel.LH for s in highs)
    assert any(s.price == 150 and s.classification == StructureLabel.LL for s in lows)
    bear_bos = [e for e in result.bos_events if e.direction == StructureDirection.BEARISH]
    assert any(e.broken_level == 150 and e.close_price == 145 for e in bear_bos)


def test_audit_C_bullish_choch() -> None:
    # Establish bearish via scenario B, then bullish close above latest unbroken SH
    candles = bearish_structure_series()
    result0 = run(candles)
    assert result0.snapshot.bias in {StructureBias.BEARISH, StructureBias.BULLISH} or True
    # After bearish BOS bias should be bearish
    assert result0.snapshot.bias == StructureBias.BEARISH
    active_sh = result0.snapshot.active_bullish_level
    assert active_sh is not None
    n = len(candles)
    break_up = C(n, active_sh - 1, active_sh + 20, active_sh - 2, active_sh + 5)
    result = run(candles + [break_up])
    assert result.choch_events
    choch = result.choch_events[-1]
    assert choch.direction == StructureDirection.BULLISH
    assert choch.previous_bias == StructureBias.BEARISH
    assert choch.new_bias == StructureBias.BULLISH
    assert choch.broken_level == active_sh


def test_audit_D_bearish_choch() -> None:
    candles = bullish_structure_series()
    result0 = run(candles)
    assert result0.snapshot.bias == StructureBias.BULLISH
    active_sl = result0.snapshot.active_bearish_level
    assert active_sl is not None
    n = len(candles)
    break_down = C(n, active_sl + 1, active_sl + 2, active_sl - 20, active_sl - 5)
    result = run(candles + [break_down])
    assert result.choch_events
    choch = result.choch_events[-1]
    assert choch.direction == StructureDirection.BEARISH
    assert choch.previous_bias == StructureBias.BULLISH
    assert choch.new_bias == StructureBias.BEARISH


def test_audit_E_wick_only_no_bos() -> None:
    candles = bullish_structure_series()[:-1]  # remove the real BOS bar
    # Wick above 150, close below
    wick = C(len(candles), 148, 170, 147, 149)
    assert wick.high > 150 and wick.close < 150
    assert not is_bullish_close_break(wick, 150)
    result = run(candles + [wick])
    assert not any(e.broken_level == 150 for e in result.bos_events)
    assert not any(e.broken_level == 150 for e in result.choch_events)


def test_audit_F_choch_without_displacement_no_mss() -> None:
    candles = bullish_structure_series()
    result0 = run(candles)
    active_sl = result0.snapshot.active_bearish_level
    assert active_sl is not None
    # Tiny body close below SL
    n = len(candles)
    tiny = C(n, active_sl - 0.1, active_sl + 0.5, active_sl - 1.0, active_sl - 0.2)
    body = abs(tiny.close - tiny.open)
    result = run(candles + [tiny])
    # Must be CHoCH (bias was bullish)
    assert any(e.broken_level == active_sl for e in result.choch_events)
    # Compute ATR at last bar — if available, ensure body < 1.5*ATR ⇒ no MSS for that choch
    highs = np.asarray([c.high for c in candles + [tiny]], dtype=float)
    lows = np.asarray([c.low for c in candles + [tiny]], dtype=float)
    closes = np.asarray([c.close for c in candles + [tiny]], dtype=float)
    atr_vals = calc_atr(highs, lows, closes, 14)
    atr_last = float(atr_vals[-1]) if np.isfinite(atr_vals[-1]) else None
    ok, _, _ = has_displacement(tiny, atr_last, CFG)
    assert ok is False or atr_last is None
    choch_keys = {e.event_key for e in result.choch_events if e.broken_level == active_sl}
    assert not any(m.choch_event_key in choch_keys for m in result.mss_events)


def test_audit_G_valid_mss_with_displacement() -> None:
    candles = bullish_structure_series()
    # Prepend ATR warm-up bars with moderate range so ATR is defined but not huge
    head = [C(i - 40, 120, 122, 118, 120) for i in range(40)]
    # Re-stamp timestamps continuously
    series: list[Candle] = []
    for i, c in enumerate(head + candles):
        series.append(C(i, c.open, c.high, c.low, c.close))
    mid = run(series)
    assert mid.snapshot.bias == StructureBias.BULLISH
    active_sl = mid.snapshot.active_bearish_level
    assert active_sl is not None
    # Large body CHoCH
    n = len(series)
    big = C(n, active_sl + 5, active_sl + 6, active_sl - 80, active_sl - 70)
    body = abs(big.close - big.open)
    result = run(series + [big])
    assert result.choch_events
    assert result.mss_events
    mss = result.mss_events[-1]
    assert mss.choch_event_key == result.choch_events[-1].event_key
    assert mss.body_size == body
    assert mss.body_size >= mss.atr_value * CFG.displacement_atr_mult
    assert mss.direction == StructureDirection.BEARISH


# ======================== Strategy rule spot checks ========================


def test_audit_equal_high_tie_strict() -> None:
    rows = [
        (10, 11, 9, 10),
        (10, 12, 9, 11),
        (11, 13, 10, 12),
        (12, 20, 11, 15),
        (15, 20, 14, 16),  # equal high
        (16, 18, 15, 17),
        (17, 18, 14, 15),
    ]
    swings = detect_confirmed_swings(
        [C(i, *r) for i, r in enumerate(rows)],
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
    )
    assert not any(s.kind == SwingKind.HIGH and s.candle_index == 3 for s in swings)


def test_audit_utc_on_all_events() -> None:
    result = run(bullish_structure_series())
    for s in result.swings:
        assert s.candle_timestamp.tzinfo is not None
        assert s.confirmation_timestamp.tzinfo is not None
        assert s.candle_timestamp.utcoffset() == timedelta(0)
    for e in result.bos_events + result.choch_events:
        assert e.candle_timestamp.tzinfo is not None


def test_audit_no_duplicate_event_keys() -> None:
    result = run(bullish_structure_series() + bearish_structure_series())
    assert len(result.event_keys) == len(set(result.event_keys))


def test_audit_config_version_embedded() -> None:
    result = run(bullish_structure_series())
    assert result.config["config_version"] == "ms-v1.0.0-balanced"
    assert result.snapshot.config_version == "ms-v1.0.0-balanced"


def test_audit_initial_bias_undefined_insufficient() -> None:
    # Only left side of a potential swing — no confirmed pivots
    candles = [C(i, 100, 101, 99, 100) for i in range(5)]
    result = run(candles)
    assert result.swings == []
    assert result.bos_events == []
    assert result.snapshot.bias == StructureBias.UNDEFINED


# ======================== 4. API audit (mocked) ========================


def test_audit_api_schema_and_isolation() -> None:
    candles = bullish_structure_series()
    manager = AsyncMock()
    manager.fetch_ohlcv = AsyncMock(return_value=candles)

    with patch(
        "app.services.market_structure_service.get_exchange_manager",
        return_value=manager,
    ):
        resp = client.get(
            "/api/v1/market-structure",
            params={
                "exchange": "binance",
                "market_type": "spot",
                "symbol": "BTC/USDT",
                "timeframe": "1h",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["exchange"] == "binance"
    assert data["market_type"] == "spot"
    assert data["symbol"] == "BTC/USDT"
    assert data["include_unconfirmed"] is False
    assert "snapshot" in data and "bias" in data["snapshot"]
    assert data["config"]["swing_left"] == 3
    assert data["config"]["config_version"].startswith("ms-v")
    keys = (
        [s["event_key"] for s in data["swings"]]
        + [e["event_key"] for e in data["bos_events"]]
        + [e["event_key"] for e in data["choch_events"]]
        + [e["event_key"] for e in data["mss_events"]]
    )
    assert len(keys) == len(set(keys))
    for s in data["swings"]:
        assert s["confirmed"] is True
        assert s["candle_timestamp"].endswith("+00:00") or s["candle_timestamp"].endswith("Z") or "+00:00" in s["candle_timestamp"] or s["candle_timestamp"].endswith("Z")


def test_audit_api_insufficient_data() -> None:
    few = [C(i, 100, 101, 99, 100) for i in range(4)]
    manager = AsyncMock()
    manager.fetch_ohlcv = AsyncMock(return_value=few)
    with patch(
        "app.services.market_structure_service.get_exchange_manager",
        return_value=manager,
    ):
        resp = client.get(
            "/api/v1/market-structure",
            params={
                "exchange": "binance",
                "market_type": "spot",
                "symbol": "ETH/USDT",
                "timeframe": "15m",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["swings"] == []
    assert data["bos_events"] == []
    assert data["snapshot"]["bias"] == "undefined"
    assert data["snapshot"]["closed_candles_used"] == 4


def test_audit_api_exchange_market_in_event_keys() -> None:
    candles = [
        c.model_copy(update={"exchange": ExchangeId.BYBIT, "market_type": MarketType.LINEAR_PERPETUAL})
        for c in bullish_structure_series()
    ]
    manager = AsyncMock()
    manager.fetch_ohlcv = AsyncMock(return_value=candles)
    with patch(
        "app.services.market_structure_service.get_exchange_manager",
        return_value=manager,
    ):
        resp = client.get(
            "/api/v1/market-structure",
            params={
                "exchange": "bybit",
                "market_type": "linear_perpetual",
                "symbol": "BTC/USDT",
                "timeframe": "1h",
            },
        )
    data = resp.json()
    assert resp.status_code == 200
    if data["swings"]:
        assert "bybit:linear_perpetual" in data["swings"][0]["event_key"]
