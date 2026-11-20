"""Phase 3.4 Order Blocks & FVG tests A–Y."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.analysis.market_structure.models import (
    BreakKind,
    MSSEvent,
    StructureBias,
    StructureBreak,
    StructureDirection,
)
from app.analysis.ob_fvg import analyze_ob_fvg
from app.analysis.ob_fvg.config import ObFvgConfig
from app.analysis.ob_fvg.engine import new_ob_fvg_events_since
from app.analysis.ob_fvg.models import FvgStatus, ObStatus, ZoneSide
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.main import app

CFG = ObFvgConfig(
    ob_max_lookback=10,
    ob_displacement_atr_mult=0.5,  # easier on flat fixtures
    fvg_min_gap_atr_mult=0.01,
    fvg_min_gap_fallback_pct=0.0001,
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


def bos(
    *,
    direction: StructureDirection,
    idx: int,
    level: float = 100.0,
    exchange: ExchangeId = ExchangeId.BINANCE,
    market_type: MarketType = MarketType.SPOT,
) -> StructureBreak:
    return StructureBreak(
        event_key=f"bos:{direction.value}:test:{idx}",
        exchange=exchange,
        symbol="BTC/USDT",
        market_type=market_type,
        timeframe=Timeframe.H1,
        break_kind=BreakKind.BOS,
        direction=direction,
        broken_level=level,
        broken_swing_key=f"swing:{idx}",
        close_price=level + (1 if direction == StructureDirection.BULLISH else -1),
        candle_timestamp=_ts(idx),
        confirmation_timestamp=_ts(idx),
        previous_bias=StructureBias.UNDEFINED,
        new_bias=StructureBias.BULLISH
        if direction == StructureDirection.BULLISH
        else StructureBias.BEARISH,
        config_version="ms-v1.0.0-balanced",
        candle_index=idx,
        body_size=5.0,
        atr_value=2.0,
    )


def base_flat(n: int = 40) -> list[Candle]:
    return [candle(i, 100, 101, 99, 100) for i in range(n)]


def test_A_bullish_ob_linked_to_bullish_bos() -> None:
    candles = base_flat(30)
    # opposing bearish candle
    candles[10] = candle(10, 105, 106, 100, 101)  # bearish
    # displacement bullish break
    candles[15] = candle(15, 102, 112, 101, 110)  # large bullish body
    result = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[bos(direction=StructureDirection.BULLISH, idx=15)],
        mss_events=[],
    )
    assert len(result.bullish_order_blocks) == 1
    ob = result.bullish_order_blocks[0]
    assert ob.side == ZoneSide.BULLISH
    assert ob.source_structure_kind.value == "bos"
    assert ob.zone_low == 100.0
    assert ob.zone_high == 106.0


def test_B_bearish_ob_linked_to_bearish_bos() -> None:
    candles = base_flat(30)
    candles[10] = candle(10, 95, 100, 94, 99)  # bullish
    candles[15] = candle(15, 98, 99, 88, 90)  # large bearish body
    result = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[bos(direction=StructureDirection.BEARISH, idx=15)],
        mss_events=[],
    )
    assert len(result.bearish_order_blocks) == 1
    assert result.bearish_order_blocks[0].zone_low == 94.0
    assert result.bearish_order_blocks[0].zone_high == 100.0


def test_C_no_opposing_candle_no_ob() -> None:
    candles = base_flat(20)
    # all flat closes == opens → neither bullish nor bearish opposing
    candles[15] = candle(15, 100, 110, 99, 109)
    result = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[bos(direction=StructureDirection.BULLISH, idx=15)],
        mss_events=[],
    )
    assert result.bullish_order_blocks == []


def test_D_no_structure_event_no_ob() -> None:
    candles = base_flat(20)
    candles[10] = candle(10, 105, 106, 100, 101)
    result = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[],
        mss_events=[],
    )
    assert result.bullish_order_blocks == []
    assert result.bearish_order_blocks == []


def test_E_duplicate_prevention() -> None:
    candles = base_flat(30)
    candles[10] = candle(10, 105, 106, 100, 101)
    candles[15] = candle(15, 102, 112, 101, 110)
    event = bos(direction=StructureDirection.BULLISH, idx=15)
    result = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[event, event],
        mss_events=[],
    )
    keys = [o.event_key for o in result.bullish_order_blocks]
    assert len(keys) == len(set(keys))
    assert len(keys) == 1


def test_F_zone_boundaries_full_candle() -> None:
    candles = base_flat(30)
    candles[10] = candle(10, 108, 110, 100, 102)
    candles[15] = candle(15, 103, 120, 102, 118)
    result = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[bos(direction=StructureDirection.BULLISH, idx=15)],
        mss_events=[],
    )
    ob = result.bullish_order_blocks[0]
    assert ob.zone_low == 100.0
    assert ob.zone_high == 110.0
    assert ob.boundary_method == "full_candle"


def test_G_partial_mitigation() -> None:
    # Keep price above the OB after the break until the intentional touch.
    candles = [candle(i, 120, 121, 119, 120) for i in range(30)]
    candles[10] = candle(10, 105, 106, 100, 101)
    candles[15] = candle(15, 102, 112, 101, 110)
    candles[18] = candle(18, 104, 105, 103, 104)  # overlaps [100,106]
    result = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[bos(direction=StructureDirection.BULLISH, idx=15)],
        mss_events=[],
    )
    assert result.bullish_order_blocks[0].status == ObStatus.PARTIALLY_MITIGATED
    assert result.bullish_order_blocks[0].first_mitigation_timestamp == _ts(18)


def test_H_full_mitigation() -> None:
    candles = [candle(i, 120, 121, 119, 120) for i in range(30)]
    candles[10] = candle(10, 105, 106, 100, 101)
    candles[15] = candle(15, 102, 112, 101, 110)
    candles[18] = candle(18, 104, 107, 99, 100)  # traverses 100–106
    result = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[bos(direction=StructureDirection.BULLISH, idx=15)],
        mss_events=[],
    )
    assert result.bullish_order_blocks[0].status == ObStatus.MITIGATED


def test_I_invalidation() -> None:
    candles = [candle(i, 120, 121, 119, 120) for i in range(30)]
    candles[10] = candle(10, 105, 106, 100, 101)
    candles[15] = candle(15, 102, 112, 101, 110)
    candles[18] = candle(18, 99, 99.5, 98, 98.5)  # close below zone_low, no full traverse of high
    result = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[bos(direction=StructureDirection.BULLISH, idx=15)],
        mss_events=[],
    )
    assert result.bullish_order_blocks[0].status == ObStatus.INVALIDATED


def test_J_ob_no_lookahead() -> None:
    candles = [candle(i, 120, 121, 119, 120) for i in range(25)]
    candles[10] = candle(10, 105, 106, 100, 101)
    candles[15] = candle(15, 102, 112, 101, 110)
    candles[20] = candle(20, 104, 107, 99, 100)  # mitigation in future
    prefix = candles[:16]
    full = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[bos(direction=StructureDirection.BULLISH, idx=15)],
        mss_events=[],
    )
    early = analyze_ob_fvg(
        prefix,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[bos(direction=StructureDirection.BULLISH, idx=15)],
        mss_events=[],
    )
    assert early.bullish_order_blocks[0].status == ObStatus.ACTIVE
    assert full.bullish_order_blocks[0].status == ObStatus.MITIGATED


def _bullish_fvg_series(n: int = 12) -> list[Candle]:
    """Isolated bullish FVG at indices 3–5; other bars stay away from the gap."""
    candles = [candle(i, 150, 151, 149, 150) for i in range(n)]
    candles[3] = candle(3, 100, 100, 99, 100)  # c1 high=100
    candles[4] = candle(4, 105, 110, 104, 109)
    candles[5] = candle(5, 111, 115, 110, 114)  # c3 low=110 → gap 100–110
    return candles


def test_K_bullish_fvg() -> None:
    # Minimal 3-candle series — only one possible FVG window
    candles = [
        candle(0, 100, 100, 99, 100),
        candle(1, 105, 110, 104, 109),
        candle(2, 111, 115, 110, 114),
    ]
    result = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[],
        mss_events=[],
    )
    assert len(result.bullish_fvgs) == 1
    fvg = result.bullish_fvgs[0]
    assert fvg.zone_low == 100.0
    assert fvg.zone_high == 110.0


def test_L_bearish_fvg() -> None:
    candles = [
        candle(0, 100, 110, 100, 105),
        candle(1, 99, 100, 90, 91),
        candle(2, 89, 95, 85, 88),
    ]
    result = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[],
        mss_events=[],
    )
    assert len(result.bearish_fvgs) == 1
    assert result.bearish_fvgs[0].zone_high == 100.0
    assert result.bearish_fvgs[0].zone_low == 95.0


def test_M_no_fvg_when_overlap() -> None:
    candles = [
        candle(0, 100, 105, 99, 104),
        candle(1, 104, 106, 103, 105),
        candle(2, 104, 107, 103, 106),
    ]
    result = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[],
        mss_events=[],
    )
    assert result.bullish_fvgs == []
    assert result.bearish_fvgs == []


def test_N_min_gap_threshold() -> None:
    strict = ObFvgConfig(
        fvg_min_gap_atr_mult=50.0,  # huge → no FVG with tiny ATR-ish series
        fvg_min_gap_fallback_pct=0.5,
    )
    candles = [candle(i, 150, 151, 149, 150) for i in range(10)]
    candles[3] = candle(3, 100, 101, 99, 100)
    candles[4] = candle(4, 102, 103, 101, 102)
    candles[5] = candle(5, 103, 104, 102.5, 103)
    result = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=strict,
        bos_events=[],
        mss_events=[],
    )
    assert result.bullish_fvgs == []


def test_O_partial_fill_pct() -> None:
    candles = [
        candle(0, 100, 100, 99, 100),
        candle(1, 105, 110, 104, 109),
        candle(2, 111, 115, 110, 114),
        candle(3, 112, 113, 111, 112),  # above gap — no fill yet
        candle(4, 104, 106, 103, 105),  # overlaps 3 of 10 → 30%
    ]
    result = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[],
        mss_events=[],
    )
    fvg = next(f for f in result.bullish_fvgs if abs(f.zone_high - 110.0) < 1e-9)
    assert fvg.status == FvgStatus.PARTIALLY_FILLED
    assert 25.0 <= fvg.max_fill_pct <= 35.0


def test_P_full_fill() -> None:
    candles = [
        candle(0, 100, 100, 99, 100),
        candle(1, 105, 110, 104, 109),
        candle(2, 111, 115, 110, 114),
        candle(3, 112, 113, 111, 112),
        candle(4, 99, 111, 98, 100),  # full traverse
    ]
    result = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[],
        mss_events=[],
    )
    fvg = next(f for f in result.bullish_fvgs if abs(f.zone_high - 110.0) < 1e-9)
    assert fvg.status == FvgStatus.FILLED
    assert fvg.max_fill_pct == 100.0


def test_Q_fvg_invalidation() -> None:
    candles = _bullish_fvg_series(12)
    # Close below gap low without fully traversing the gap high → invalidated
    candles[7] = candle(7, 99, 99.5, 98, 98.5)
    result = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[],
        mss_events=[],
    )
    target = next(f for f in result.bullish_fvgs if f.zone_low == 100.0 and f.zone_high == 110.0)
    assert target.status == FvgStatus.INVALIDATED


def test_R_forming_candle_no_confirmed_fvg() -> None:
    candles = [
        candle(0, 100, 100, 99, 100),
        candle(1, 105, 110, 104, 109),
        candle(2, 111, 115, 110, 114, closed=False),
    ]
    result = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[],
        mss_events=[],
        include_unconfirmed=True,
    )
    assert result.bullish_fvgs == []
    assert len(result.provisional_fvgs) >= 1
    assert all(not f.confirmed for f in result.provisional_fvgs)


def test_S_fvg_no_lookahead() -> None:
    early_candles = [
        candle(0, 100, 100, 99, 100),
        candle(1, 105, 110, 104, 109),
        candle(2, 111, 115, 110, 114),
    ]
    full_candles = early_candles + [
        candle(3, 112, 113, 111, 112),
        candle(4, 99, 111, 98, 100),
    ]
    early = analyze_ob_fvg(
        early_candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[],
        mss_events=[],
    )
    full = analyze_ob_fvg(
        full_candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[],
        mss_events=[],
    )
    assert early.bullish_fvgs[0].status == FvgStatus.ACTIVE
    target = next(f for f in full.bullish_fvgs if abs(f.zone_high - 110.0) < 1e-9)
    assert target.status == FvgStatus.FILLED


def test_T_prefix_equivalence() -> None:
    candles = _bullish_fvg_series(20)
    full = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[],
        mss_events=[],
    )
    prefix = analyze_ob_fvg(
        candles[:6],
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[],
        mss_events=[],
    )
    assert [f.event_key for f in prefix.bullish_fvgs] == [
        f.event_key for f in full.bullish_fvgs if f.detection_timestamp <= _ts(5)
    ]


def test_U_reconnect_dedupe() -> None:
    candles = _bullish_fvg_series(20)
    a = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[],
        mss_events=[],
    )
    b = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[],
        mss_events=[],
    )
    fresh = new_ob_fvg_events_since(b, set(a.event_keys))
    assert fresh["bullish_fvgs"] == []
    assert fresh["bearish_fvgs"] == []


def test_V_api_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    candles = _bullish_fvg_series(20)

    class _Mgr:
        async def fetch_ohlcv(self, *args, **kwargs):
            return candles

    from app.services import ob_fvg_service as svc

    monkeypatch.setattr(svc, "get_exchange_manager", lambda: _Mgr())
    client = TestClient(app)
    resp = client.get(
        "/api/v1/ob-fvg",
        params={
            "exchange": "binance",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "limit": 100,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "bullish_fvgs" in body
    assert "bearish_order_blocks" in body
    assert body["config"]["config_version"] == "obfvg-v1.0.0-balanced"
    assert body["snapshot"]["bullish_fvg_count"] == len(body["bullish_fvgs"])


def test_W_isolation_in_keys() -> None:
    candles = _bullish_fvg_series(10)
    a = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[],
        mss_events=[],
    )
    b = analyze_ob_fvg(
        [
            Candle(
                timestamp=c.timestamp,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
                exchange=ExchangeId.BYBIT,
                symbol="ETH/USDT",
                market_type=MarketType.LINEAR_PERPETUAL,
                is_closed=c.is_closed,
            )
            for c in candles
        ],
        exchange=ExchangeId.BYBIT,
        symbol="ETH/USDT",
        market_type=MarketType.LINEAR_PERPETUAL,
        timeframe=Timeframe.H4,
        config=CFG,
        bos_events=[],
        mss_events=[],
    )
    assert a.bullish_fvgs[0].event_key != b.bullish_fvgs[0].event_key
    assert "binance:spot:BTC/USDT:1h" in a.bullish_fvgs[0].event_key
    assert "bybit" in b.bullish_fvgs[0].event_key


def test_X_utc_timestamps() -> None:
    candles = _bullish_fvg_series(10)
    result = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[],
        mss_events=[],
    )
    fvg = result.bullish_fvgs[0]
    assert fvg.detection_timestamp.tzinfo is not None
    assert fvg.detection_timestamp.utcoffset() == timedelta(0)


def test_Y_mss_also_creates_ob() -> None:
    candles = base_flat(30)
    candles[10] = candle(10, 105, 106, 100, 101)
    candles[15] = candle(15, 102, 112, 101, 110)
    mss = MSSEvent(
        event_key="mss:bullish:test:15",
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        direction=StructureDirection.BULLISH,
        choch_event_key="choch:x",
        broken_level=105.0,
        close_price=110.0,
        candle_timestamp=_ts(15),
        confirmation_timestamp=_ts(15),
        body_size=8.0,
        atr_value=2.0,
        displacement_mult=1.5,
        previous_bias=StructureBias.BEARISH,
        new_bias=StructureBias.BULLISH,
        config_version="ms-v1.0.0-balanced",
    )
    result = analyze_ob_fvg(
        candles,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.H1,
        config=CFG,
        bos_events=[],
        mss_events=[mss],
    )
    assert len(result.bullish_order_blocks) == 1
    assert result.bullish_order_blocks[0].source_structure_kind.value == "mss"
