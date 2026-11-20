"""Phase 5.2.1 — Historical Analysis Pipeline tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.main import app
from app.replay.analysis.pipeline import run_historical_analysis
from app.replay.analysis.validation import LookAheadError, assert_no_future_candles
from app.replay.manager import reset_replay_manager
from app.replay.timeline import candle_close_time, closed_candles_as_of

EX = ExchangeId.BINANCE
SYM = "BTC/USDT"
MT = MarketType.SPOT
UTC = timezone.utc
START = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)


def _tf_sec(tf: Timeframe) -> int:
    return {Timeframe.M5: 300, Timeframe.M15: 900, Timeframe.H1: 3600, Timeframe.H4: 14400}[tf]


def _c(open_ts: datetime, o: float, h: float, l: float, cl: float, *, tf: Timeframe) -> Candle:
    return Candle(
        timestamp=open_ts,
        open=o,
        high=h,
        low=l,
        close=cl,
        volume=10.0,
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        is_closed=True,
        close_time=open_ts + timedelta(seconds=_tf_sec(tf)) - timedelta(milliseconds=1),
    )


def _synth(n_5m: int = 120) -> dict[Timeframe, list[Candle]]:
    """Enough bars for indicator warm-up + structure."""
    m5: list[Candle] = []
    price = 100.0
    for i in range(n_5m):
        ts = START + timedelta(minutes=5 * i)
        # Mild trend with occasional swings
        delta = 0.4 if (i // 8) % 2 == 0 else -0.35
        o = price
        cl = price + delta
        h = max(o, cl) + 0.3
        l = min(o, cl) - 0.3
        m5.append(_c(ts, o, h, l, cl, tf=Timeframe.M5))
        price = cl

    def agg(tf: Timeframe) -> list[Candle]:
        step = _tf_sec(tf)
        buckets: dict[datetime, list[Candle]] = {}
        for c in m5:
            open_sec = (int(c.timestamp.timestamp()) // step) * step
            key = datetime.fromtimestamp(open_sec, tz=UTC)
            buckets.setdefault(key, []).append(c)
        out = []
        for open_ts in sorted(buckets):
            parts = buckets[open_ts]
            out.append(
                _c(
                    open_ts,
                    parts[0].open,
                    max(p.high for p in parts),
                    min(p.low for p in parts),
                    parts[-1].close,
                    tf=tf,
                )
            )
        return out

    return {
        Timeframe.M5: m5,
        Timeframe.M15: agg(Timeframe.M15),
        Timeframe.H1: agg(Timeframe.H1),
        Timeframe.H4: agg(Timeframe.H4),
    }


@pytest.fixture(autouse=True)
def _reset():
    reset_replay_manager()
    yield
    reset_replay_manager()


def test_future_candles_rejected():
    series = _synth(12)
    clock = candle_close_time(series[Timeframe.M5][0], Timeframe.M5)
    future = series[Timeframe.M5][5]
    with pytest.raises(LookAheadError):
        assert_no_future_candles(
            [series[Timeframe.M5][0], future],
            timeframe=Timeframe.M5,
            clock=clock,
        )


def test_prefix_excludes_future_from_closed_as_of():
    series = _synth(20)
    clock = candle_close_time(series[Timeframe.M5][3], Timeframe.M5)
    prefix = closed_candles_as_of(series[Timeframe.M5], Timeframe.M5, clock)
    assert len(prefix) == 4
    for c in prefix:
        assert candle_close_time(c, Timeframe.M5) <= clock


def test_pipeline_determinism_same_prefix():
    series = _synth(100)
    clock = candle_close_time(series[Timeframe.M5][80], Timeframe.M5)
    a = run_historical_analysis(
        session_id="s1",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=series,
        clock=clock,
        event_index=80,
    )
    b = run_historical_analysis(
        session_id="s1",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=series,
        clock=clock,
        event_index=80,
    )
    assert a.decision == b.decision
    assert a.bullish_score == b.bullish_score
    assert a.bearish_score == b.bearish_score
    assert a.lifecycle_status == b.lifecycle_status
    assert a.closed_candle_counts == b.closed_candle_counts
    assert a.structure.keys() == b.structure.keys()


def test_prefix_invariance_complete_pipeline():
    """Appending future candles must not change analysis at earlier T."""
    series = _synth(100)
    clock = candle_close_time(series[Timeframe.M5][60], Timeframe.M5)
    prefix_only = {
        tf: closed_candles_as_of(candles, tf, clock) for tf, candles in series.items()
    }
    early = run_historical_analysis(
        session_id="inv",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=prefix_only,
        clock=clock,
        event_index=60,
    )
    # Full series includes future bars after clock
    full = run_historical_analysis(
        session_id="inv",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=series,
        clock=clock,
        event_index=60,
    )
    assert early.decision == full.decision
    assert early.decision_reason == full.decision_reason
    assert early.bullish_score == full.bullish_score
    assert early.bearish_score == full.bearish_score
    assert early.lifecycle_status == full.lifecycle_status
    assert early.stop_loss == full.stop_loss
    assert early.take_profit_levels == full.take_profit_levels
    assert early.risk_reward == full.risk_reward
    assert early.closed_candle_counts == full.closed_candle_counts
    for tf in ("5m", "15m", "1h", "4h"):
        assert early.structure.get(tf) == full.structure.get(tf)
        assert early.liquidity.get(tf) == full.liquidity.get(tf)
        assert early.ob_fvg.get(tf) == full.ob_fvg.get(tf)
        # Indicator latest values must match
        ea = early.indicators.get(tf)
        fa = full.indicators.get(tf)
        if ea and fa:
            assert ea.values == fa.values
            assert ea.closed_candles_used == fa.closed_candles_used


def test_htf_future_close_cannot_affect_early_confluence():
    series = _synth(100)
    # Early clock: before first 1h close completes many bars
    clock = candle_close_time(series[Timeframe.M5][2], Timeframe.M5)
    snap = run_historical_analysis(
        session_id="htf",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=series,
        clock=clock,
        event_index=2,
    )
    assert snap.closed_candle_counts.get("1h", 0) == 0
    assert snap.closed_candle_counts.get("4h", 0) == 0
    # Decision must not claim complete HTF readiness incorrectly
    assert snap.closed_candle_counts.get("5m", 0) == 3


def test_speed_does_not_change_analysis():
    series = _synth(90)
    clock = candle_close_time(series[Timeframe.M5][70], Timeframe.M5)
    results = [
        run_historical_analysis(
            session_id="spd",
            exchange=EX,
            symbol=SYM,
            market_type=MT,
            series_by_tf=series,
            clock=clock,
            event_index=70,
        )
        for _ in range(3)
    ]
    assert results[0].bullish_score == results[1].bullish_score == results[2].bullish_score
    assert results[0].decision == results[2].decision


def test_spot_never_executable_short_in_historical():
    series = _synth(120)
    clock = candle_close_time(series[Timeframe.M5][100], Timeframe.M5)
    snap = run_historical_analysis(
        session_id="spot",
        exchange=EX,
        symbol=SYM,
        market_type=MarketType.SPOT,
        series_by_tf=series,
        clock=clock,
        event_index=100,
    )
    assert snap.decision != "SHORT"


def test_api_enable_analysis_and_history():
    series = _synth(80)

    async def fake_load(**kwargs):
        return series, [], []

    client = TestClient(app)
    with patch("app.replay.session.load_replay_series", new=AsyncMock(side_effect=fake_load)):
        created = client.post(
            "/api/v1/replay/sessions",
            json={
                "exchange": "binance",
                "symbol": "BTC/USDT",
                "market_type": "spot",
                "start_time": START.isoformat(),
                "end_time": (START + timedelta(hours=6)).isoformat(),
                "speed": "max",
            },
        )
        assert created.status_code == 200, created.text
        sid = created.json()["session"]["session_id"]

        enabled = client.post(f"/api/v1/replay/sessions/{sid}/analysis/enable")
        assert enabled.status_code == 200, enabled.text
        body = enabled.json()
        assert body["analysis_enabled"] is True
        assert body["snapshot"] is not None
        assert "decision" in body["snapshot"]

        current = client.get(f"/api/v1/replay/sessions/{sid}/analysis")
        assert current.status_code == 200
        assert current.json()["snapshot"]["decision"] == body["snapshot"]["decision"]

        # Step and ensure new analysis stored
        step = client.post(f"/api/v1/replay/sessions/{sid}/step")
        assert step.status_code == 200
        hist = client.get(f"/api/v1/replay/sessions/{sid}/analysis/history")
        assert hist.status_code == 200
        assert hist.json()["total"] >= 1

        # Disable
        disabled = client.post(f"/api/v1/replay/sessions/{sid}/analysis/disable")
        assert disabled.json()["analysis_enabled"] is False


def test_reset_reuses_cached_analysis_at_index_zero():
    series = _synth(60)

    async def fake_load(**kwargs):
        return series, [], []

    client = TestClient(app)
    with patch("app.replay.session.load_replay_series", new=AsyncMock(side_effect=fake_load)):
        sid = client.post(
            "/api/v1/replay/sessions",
            json={
                "exchange": "binance",
                "symbol": "BTC/USDT",
                "market_type": "spot",
                "start_time": START.isoformat(),
                "end_time": (START + timedelta(hours=4)).isoformat(),
                "speed": "max",
            },
        ).json()["session"]["session_id"]
        first = client.post(f"/api/v1/replay/sessions/{sid}/analysis/enable").json()["snapshot"]
        client.post(f"/api/v1/replay/sessions/{sid}/step")
        client.post(f"/api/v1/replay/sessions/{sid}/step")
        reset = client.post(f"/api/v1/replay/sessions/{sid}/reset")
        assert reset.status_code == 200
        again = client.get(f"/api/v1/replay/sessions/{sid}/analysis").json()["snapshot"]
        assert again["event_index"] == 0
        assert again["decision"] == first["decision"]
        assert again["bullish_score"] == first["bullish_score"]
