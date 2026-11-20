"""Phase 4.1 — Multi-Timeframe orchestration tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.analysis.multi_timeframe.config import DEFAULT_MTF_CONFIG, MTF_LADDER, MultiTimeframeConfig
from app.analysis.multi_timeframe.orchestrator import (
    apply_candle_update,
    build_snapshot,
    detect_gaps,
    evaluate_timeframe_series,
    sanitize_candles,
    split_closed_and_forming,
)
from app.exchanges.exceptions import ExchangeError
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.main import app
from app.market_data.stream_manager import StreamManager
from app.market_data.ws_messages import CandleData, MarketWsMessage, WsMessageType


def _ts(i: int, *, base: datetime | None = None, step_min: int = 5) -> datetime:
    origin = base or datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    return origin + timedelta(minutes=step_min * i)


def candle(
    i: int,
    *,
    timeframe_step: int = 5,
    closed: bool = True,
    o: float = 100.0,
    h: float | None = None,
    low: float | None = None,
    c: float = 101.0,
    vol: float = 10.0,
    exchange: ExchangeId = ExchangeId.BINANCE,
    symbol: str = "BTC/USDT",
    market_type: MarketType = MarketType.SPOT,
) -> Candle:
    open_ = o
    close = c
    high = h if h is not None else max(open_, close) + 1
    lo = low if low is not None else min(open_, close) - 1
    ts = _ts(i, step_min=timeframe_step)
    close_time = ts + timedelta(minutes=timeframe_step) - timedelta(milliseconds=1)
    return Candle(
        timestamp=ts,
        open=open_,
        high=high,
        low=lo,
        close=close,
        volume=vol,
        exchange=exchange,
        symbol=symbol,
        market_type=market_type,
        is_closed=closed,
        close_time=close_time if closed else None,
    )


def series(n: int, *, step: int = 5, closed_last: bool = True) -> list[Candle]:
    out = [candle(i, timeframe_step=step, closed=True) for i in range(n - 1)]
    out.append(candle(n - 1, timeframe_step=step, closed=closed_last, o=100, c=102))
    return out


# --- Config ---


def test_mtf_ladder_four_timeframes():
    assert MTF_LADDER == (Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5)
    assert DEFAULT_MTF_CONFIG.config_version == "mtf-v1.0.0-orchestration"
    for tf in MTF_LADDER:
        hist = DEFAULT_MTF_CONFIG.history_for(tf)
        assert hist.fetch_limit >= 50
        assert hist.min_closed_candles >= 1


# --- Normalization / ordering / duplicates / OHLC ---


def test_sanitize_sorts_dedupes_and_drops_invalid():
    as_of = _ts(10)
    raw = [
        candle(2),
        candle(1),
        candle(2, o=110, c=111),  # duplicate ts — last wins
    ]
    # invalid OHLC — bypass model validator; sanitize must drop
    bad = Candle.model_construct(
        timestamp=_ts(4),
        open=100.0,
        high=50.0,
        low=40.0,
        close=99.0,
        volume=1.0,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        is_closed=True,
        close_time=None,
        quote_volume=None,
        trades=None,
    )
    raw.append(bad)
    future = candle(20)
    raw.append(future)

    out = sanitize_candles(
        raw,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        as_of=as_of,
    )
    assert [c.timestamp for c in out] == sorted(c.timestamp for c in out)
    assert sum(1 for c in out if c.timestamp == _ts(2)) == 1
    assert out[[c.timestamp for c in out].index(_ts(2))].close == 111
    assert all(c.timestamp <= as_of for c in out)
    assert all(is_ok(c) for c in out)


def is_ok(c: Candle) -> bool:
    from app.market_data.normalizer import is_valid_ohlc

    return is_valid_ohlc(c.open, c.high, c.low, c.close, c.volume)


# --- Closed vs forming / no lookahead ---


def test_split_closed_forming_and_no_lookahead():
    as_of = _ts(5)
    candles = series(6, closed_last=False)
    # Inject a "closed" candle that closes in the future relative to as_of
    sneaky = candle(4, closed=True)
    sneaky = sneaky.model_copy(
        update={"close_time": as_of + timedelta(hours=1), "is_closed": True}
    )
    candles[4] = sneaky

    closed, forming = split_closed_and_forming(candles, as_of=as_of)
    assert forming is not None
    assert forming.is_closed is False
    assert all(c.is_closed for c in closed)
    assert all(
        c.close_time is None or c.close_time <= as_of for c in closed
    )
    # unfinished never in closed
    assert all(c.timestamp != candles[-1].timestamp or c.is_closed for c in closed)
    assert candles[-1].timestamp == forming.timestamp


def test_evaluate_never_marks_forming_as_confirmed_ready_path():
    cfg = MultiTimeframeConfig(
        history={
            "5m": DEFAULT_MTF_CONFIG.history_for(Timeframe.M5).model_copy(
                update={"min_closed_candles": 3}
            )
        }
    )
    candles = series(5, closed_last=False)
    as_of = candles[-1].timestamp + timedelta(minutes=1)
    summary = evaluate_timeframe_series(
        candles,
        timeframe=Timeframe.M5,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        as_of=as_of,
        config=cfg,
    )
    assert summary.forming_candle is not None
    assert summary.forming_candle.is_closed is False
    assert summary.closed_candles_count == 4
    assert all(c.is_closed for c in summary.recent_closed_candles)


# --- Gaps / stale / insufficient ---


def test_detect_gaps():
    a = candle(0, timeframe_step=5)
    b = candle(1, timeframe_step=5)
    # skip indices 2,3 → jump
    c = candle(4, timeframe_step=5)
    gaps = detect_gaps([a, b, c], Timeframe.M5, gap_factor=1.5)
    assert len(gaps) == 1
    assert gaps[0].missing_estimate >= 1


def test_insufficient_and_stale():
    cfg = MultiTimeframeConfig(
        stale_intervals=1,
        history={
            "5m": DEFAULT_MTF_CONFIG.history_for(Timeframe.M5).model_copy(
                update={"min_closed_candles": 10}
            )
        },
    )
    short = series(4, closed_last=True)
    as_of = short[-1].close_time + timedelta(minutes=1)
    s = evaluate_timeframe_series(
        short,
        timeframe=Timeframe.M5,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        as_of=as_of,
        config=cfg,
    )
    assert s.data_quality == "insufficient"
    assert not s.is_ready

    enough = series(12, closed_last=True)
    stale_as_of = enough[-1].close_time + timedelta(minutes=20)
    s2 = evaluate_timeframe_series(
        enough,
        timeframe=Timeframe.M5,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        as_of=stale_as_of,
        config=cfg,
    )
    assert s2.is_stale
    assert s2.data_quality == "stale"
    assert not s2.is_ready


def test_partial_timeframe_error_does_not_substitute():
    ok = evaluate_timeframe_series(
        series(60, step=60),
        timeframe=Timeframe.H1,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        as_of=_ts(60, step_min=60) + timedelta(minutes=1),
        config=DEFAULT_MTF_CONFIG,
    )
    bad = evaluate_timeframe_series(
        [],
        timeframe=Timeframe.M15,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        as_of=_ts(60, step_min=60),
        config=DEFAULT_MTF_CONFIG,
        error="timeout",
    )
    snap = build_snapshot(
        {Timeframe.H1: ok, Timeframe.M15: bad, Timeframe.H4: bad, Timeframe.M5: bad},
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
    )
    assert snap.overall_status == "partial"
    assert Timeframe.M15 in snap.unavailable_timeframes
    assert bad.data_quality == "error"
    assert "timeout" in (bad.status_detail or "")


def test_apply_candle_update_upsert():
    base = series(3, closed_last=True)
    upd = candle(2, closed=True, c=200)
    out = apply_candle_update(base, upd, max_candles=10)
    assert len(out) == 3
    assert out[-1].close == 200


# --- Stream manager multi-TF ---


def test_stream_manager_keeps_multiple_timeframes_per_symbol():
    import asyncio

    manager = StreamManager()

    async def _run() -> None:
        await manager.subscribe(
            "c1",
            exchange=ExchangeId.BINANCE,
            market_type=MarketType.SPOT,
            symbol="BTC/USDT",
            timeframe=Timeframe.M5,
        )
        await manager.subscribe(
            "c1",
            exchange=ExchangeId.BINANCE,
            market_type=MarketType.SPOT,
            symbol="BTC/USDT",
            timeframe=Timeframe.M15,
        )
        tfs = {t.timeframe for t in manager._topics.values()}
        assert Timeframe.M5 in tfs
        assert Timeframe.M15 in tfs
        # Rebuild merge should retain both
        await manager._rebuild_stream(ExchangeId.BINANCE, MarketType.SPOT)
        stream = manager._streams.get((ExchangeId.BINANCE, MarketType.SPOT))
        assert stream is not None
        desired_tfs = {t.timeframe for t in stream._desired.values() if t.timeframe}
        assert Timeframe.M5 in desired_tfs
        assert Timeframe.M15 in desired_tfs
        await manager.unsubscribe_client("c1")
        await manager.stop()

    asyncio.run(_run())


# --- REST ---


def test_api_schema_and_partial_failure(monkeypatch):
    async def fake_fetch(exchange, symbol, timeframe, market_type, limit=500, **_):
        if timeframe == Timeframe.M15:
            raise ExchangeError("simulated 15m failure")
        step = {Timeframe.H4: 240, Timeframe.H1: 60, Timeframe.M5: 5}[timeframe]
        return series(60, step=step, closed_last=True)

    mock_mgr = MagicMock()
    mock_mgr.fetch_ohlcv = AsyncMock(side_effect=fake_fetch)
    monkeypatch.setattr(
        "app.services.multi_timeframe_service.get_exchange_manager",
        lambda: mock_mgr,
    )

    client = TestClient(app)
    res = client.get(
        "/api/v1/multi-timeframe",
        params={
            "exchange": "binance",
            "market_type": "spot",
            "symbol": "BTC/USDT",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["snapshot"]["config_version"] == "mtf-v1.0.0-orchestration"
    assert "timeframes" in body
    assert body["sync"]["as_of"]
    assert body["metadata"]["no_trade_decisions"] is True
    qualities = {t["timeframe"]: t["data_quality"] for t in body["timeframes"]}
    assert qualities["15m"] == "error"
    # No LONG/SHORT/WAIT fields
    blob = res.text
    assert "LONG" not in blob
    assert "SHORT" not in blob
    assert "NO TRADE" not in blob


# --- WS runtime ---


@pytest.mark.asyncio
async def test_mtf_runtime_confirmed_vs_forming(monkeypatch):
    from app.market_data.multi_timeframe_runtime import MultiTimeframeRuntime

    async def fake_fetch(*_a, **_k):
        return series(55, step=5, closed_last=True)

    mock_mgr = MagicMock()
    mock_mgr.fetch_ohlcv = AsyncMock(side_effect=fake_fetch)
    monkeypatch.setattr(
        "app.market_data.multi_timeframe_runtime.get_exchange_manager",
        lambda: mock_mgr,
    )

    sm = StreamManager()
    monkeypatch.setattr(
        "app.market_data.multi_timeframe_runtime.get_stream_manager",
        lambda: sm,
    )

    rt = MultiTimeframeRuntime()
    msg = await rt.subscribe(
        "client-a",
        exchange=ExchangeId.BINANCE,
        market_type=MarketType.SPOT,
        symbol="BTC/USDT",
    )
    assert msg.type == WsMessageType.MULTI_TIMEFRAME_UPDATE
    assert msg.data["kind"] == "snapshot"  # type: ignore[index]

    # Forming update
    forming = MarketWsMessage(
        type=WsMessageType.CANDLE_UPDATE,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.M5,
        data=CandleData(
            timestamp=_ts(100),
            open=1,
            high=2,
            low=0.5,
            close=1.5,
            volume=1,
            is_closed=False,
            timeframe=Timeframe.M5,
        ),
    )
    out = await rt.on_market_message(forming)
    assert out is not None
    assert out.data["forming_candle"] is not None  # type: ignore[index]
    assert out.data["confirmed_candle"] is None  # type: ignore[index]

    closed = MarketWsMessage(
        type=WsMessageType.CANDLE_UPDATE,
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        timeframe=Timeframe.M5,
        data=CandleData(
            timestamp=_ts(101),
            open=1,
            high=2,
            low=0.5,
            close=1.5,
            volume=1,
            is_closed=True,
            timeframe=Timeframe.M5,
        ),
    )
    out2 = await rt.on_market_message(closed)
    assert out2 is not None
    assert out2.data["confirmed_candle"] is not None  # type: ignore[index]
    assert out2.data["confirmed_candle"]["is_closed"] is True  # type: ignore[index]

    await rt.unsubscribe_streams("client-a")
    await sm.stop()
