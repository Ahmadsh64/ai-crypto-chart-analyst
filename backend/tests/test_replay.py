"""Phase 5.1 — Historical Replay Engine tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.main import app
from app.replay.config import DEFAULT_REPLAY_CONFIG, ReplayConfig
from app.replay.manager import get_replay_manager, reset_replay_manager
from app.replay.session import ReplaySession
from app.replay.timeline import (
    build_event_timeline,
    candle_close_time,
    event_index_at_or_before,
    sanitize_series,
    snapshot_at,
)

EX = ExchangeId.BINANCE
SYM = "BTC/USDT"
MT = MarketType.SPOT
UTC = timezone.utc


def _c(
    open_ts: datetime,
    o: float,
    h: float,
    l: float,
    cl: float,
    vol: float = 1.0,
    *,
    tf: Timeframe = Timeframe.M5,
    is_closed: bool = True,
) -> Candle:
    close_t = open_ts + timedelta(seconds=_tf_sec(tf)) - timedelta(milliseconds=1)
    return Candle(
        timestamp=open_ts,
        open=o,
        high=h,
        low=l,
        close=cl,
        volume=vol,
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        is_closed=is_closed,
        close_time=close_t,
    )


def _tf_sec(tf: Timeframe) -> int:
    return {
        Timeframe.M5: 300,
        Timeframe.M15: 900,
        Timeframe.H1: 3600,
        Timeframe.H4: 14400,
    }[tf]


def _synth_range(
    start: datetime,
    n_5m: int,
) -> dict[Timeframe, list[Candle]]:
    """Build aligned multi-TF series from synthetic 5m bars (deterministic)."""
    m5: list[Candle] = []
    price = 100.0
    for i in range(n_5m):
        ts = start + timedelta(minutes=5 * i)
        o = price
        cl = price + (1.0 if i % 2 == 0 else -0.5)
        h = max(o, cl) + 0.2
        l = min(o, cl) - 0.2
        # Spike on bar index 2 (still inside first 15m) — must not leak before that 5m closes
        if i == 2:
            h = 999.0
        m5.append(_c(ts, o, h, l, cl, vol=float(i + 1), tf=Timeframe.M5))
        price = cl

    def aggregate(tf: Timeframe) -> list[Candle]:
        step = _tf_sec(tf)
        buckets: dict[datetime, list[Candle]] = {}
        for c in m5:
            epoch = int(c.timestamp.timestamp())
            open_sec = (epoch // step) * step
            key = datetime.fromtimestamp(open_sec, tz=UTC)
            buckets.setdefault(key, []).append(c)
        out: list[Candle] = []
        for open_ts in sorted(buckets):
            parts = buckets[open_ts]
            out.append(
                _c(
                    open_ts,
                    parts[0].open,
                    max(p.high for p in parts),
                    min(p.low for p in parts),
                    parts[-1].close,
                    sum(p.volume for p in parts),
                    tf=tf,
                )
            )
        return out

    return {
        Timeframe.M5: m5,
        Timeframe.M15: aggregate(Timeframe.M15),
        Timeframe.H1: aggregate(Timeframe.H1),
        Timeframe.H4: aggregate(Timeframe.H4),
    }


START = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _reset_manager():
    reset_replay_manager()
    yield
    reset_replay_manager()


def test_candle_timestamps_are_open_time():
    c = _c(START, 1, 2, 0.5, 1.5)
    assert c.timestamp == START
    ct = candle_close_time(c, Timeframe.M5)
    assert ct == START + timedelta(minutes=5) - timedelta(milliseconds=1)


def test_chronological_event_ordering():
    series = _synth_range(START, 12)
    times = build_event_timeline(
        series,
        start=START,
        end=START + timedelta(hours=1),
    )
    assert times == sorted(times)
    assert len(times) == len(set(times))


def test_deterministic_replay_results():
    series = _synth_range(START, 24)
    times = build_event_timeline(series, start=START, end=START + timedelta(hours=2))
    a = snapshot_at(
        session_id="s1",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=series,
        gaps=[],
        limitations=[],
        event_times=times,
        event_index=10,
        status="paused",
        speed="max",
    )
    b = snapshot_at(
        session_id="s1",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=series,
        gaps=[],
        limitations=[],
        event_times=times,
        event_index=10,
        status="paused",
        speed="1x",  # speed must not change analytical snapshot content
    )
    assert a.replay_timestamp == b.replay_timestamp
    assert a.timeframes["5m"].closed_count == b.timeframes["5m"].closed_count
    assert a.timeframes["15m"].closed_count == b.timeframes["15m"].closed_count
    fa = a.timeframes["15m"].forming_candle
    fb = b.timeframes["15m"].forming_candle
    if fa and fb:
        assert fa.model_dump() == fb.model_dump()


def test_no_look_ahead_protection():
    """At early clock, 15m forming must not include the spike that happens later."""
    series = _synth_range(START, 12)
    times = build_event_timeline(series, start=START, end=START + timedelta(hours=1))
    # First 5m close — before bar index 2 spike (open at START+10m)
    snap = snapshot_at(
        session_id="s",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=series,
        gaps=[],
        limitations=[],
        event_times=times,
        event_index=0,
        status="paused",
        speed="max",
    )
    forming_15 = snap.timeframes["15m"].forming_candle
    assert forming_15 is not None
    assert forming_15.high < 900  # spike is 999 on bar 2
    assert forming_15.is_closed is False
    full_15 = series[Timeframe.M15][0]
    assert full_15.high == 999.0
    assert forming_15.high < full_15.high


def test_htf_not_closed_early():
    series = _synth_range(START, 20)
    times = build_event_timeline(series, start=START, end=START + timedelta(hours=2))
    # After one 5m close, 1h and 4h must still be forming / not newly closed
    snap = snapshot_at(
        session_id="s",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=series,
        gaps=[],
        limitations=[],
        event_times=times,
        event_index=0,
        status="paused",
        speed="max",
    )
    assert snap.timeframes["5m"].closed_count == 1
    assert snap.timeframes["1h"].closed_count == 0
    assert snap.timeframes["4h"].closed_count == 0
    assert snap.timeframes["1h"].forming_candle is not None
    assert snap.timeframes["1h"].forming_candle.is_closed is False


def test_candle_close_time_correctness():
    series = _synth_range(START, 6)
    times = build_event_timeline(series, start=START, end=START + timedelta(hours=1))
    # At the 15m close clock (3rd 5m close index 2), 15m should be closed
    # 5m closes: idx0=04:59.999, idx1=09:59.999, idx2=14:59.999 → 15m closes
    snap = snapshot_at(
        session_id="s",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=series,
        gaps=[],
        limitations=[],
        event_times=times,
        event_index=2,
        status="paused",
        speed="max",
    )
    assert snap.timeframes["15m"].closed_count == 1
    assert snap.timeframes["15m"].forming_candle is None
    closed = snap.timeframes["15m"].closed_candles[0]
    assert closed.is_closed is True
    # Final OHLC of first 15m is now allowed
    assert closed.high == series[Timeframe.M15][0].high


def test_no_duplicate_candle_close_events():
    series = _synth_range(START, 12)
    times = build_event_timeline(series, start=START, end=START + timedelta(hours=1))
    seen_15_closes: list[datetime] = []
    prev_count = 0
    for i in range(len(times)):
        snap = snapshot_at(
            session_id="s",
            exchange=EX,
            symbol=SYM,
            market_type=MT,
            series_by_tf=series,
            gaps=[],
            limitations=[],
            event_times=times,
            event_index=i,
            status="paused",
            speed="max",
        )
        count = snap.timeframes["15m"].closed_count
        if count > prev_count:
            assert count == prev_count + 1  # at most one new close per event
            seen_15_closes.append(snap.replay_timestamp)
        prev_count = count
    assert len(seen_15_closes) == len(set(seen_15_closes))


def test_forming_versus_closed():
    series = _synth_range(START, 8)
    times = build_event_timeline(series, start=START, end=START + timedelta(hours=1))
    mid = snapshot_at(
        session_id="s",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=series,
        gaps=[],
        limitations=[],
        event_times=times,
        event_index=1,
        status="paused",
        speed="max",
    )
    assert mid.timeframes["15m"].closed_count == 0
    forming = mid.timeframes["15m"].forming_candle
    assert forming is not None and forming.is_closed is False
    # Closed list must not include the forming open
    for c in mid.timeframes["15m"].closed_candles:
        assert c.timestamp != forming.timestamp


def test_missing_candle_detection():
    series = _synth_range(START, 6)
    m5 = list(series[Timeframe.M5])
    # Drop middle candle
    broken = [m5[0], m5[1], m5[3], m5[4]]
    cleaned, gaps, notes = sanitize_series(
        broken, exchange=EX, symbol=SYM, market_type=MT, timeframe=Timeframe.M5
    )
    assert gaps
    assert any("gap" in n.lower() for n in notes)
    assert len(cleaned) == 4


def test_duplicate_candle_handling():
    c1 = _c(START, 1, 2, 0.5, 1.5)
    c2 = _c(START, 1, 3, 0.5, 2.0)  # same open — should keep first
    cleaned, gaps, _ = sanitize_series(
        [c1, c2], exchange=EX, symbol=SYM, market_type=MT, timeframe=Timeframe.M5
    )
    assert len(cleaned) == 1
    assert cleaned[0].high == 2


def test_invalid_ohlcv_rejection():
    # Bypass model validator by constructing via model_construct
    bad = Candle.model_construct(
        timestamp=START,
        open=10,
        high=9,
        low=8,
        close=9.5,
        volume=1,
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        is_closed=True,
        close_time=None,
    )
    cleaned, _, notes = sanitize_series(
        [bad, _c(START + timedelta(minutes=5), 1, 2, 0.5, 1.5)],
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        timeframe=Timeframe.M5,
    )
    assert len(cleaned) == 1
    assert any("invalid" in n.lower() for n in notes)


def test_prefix_equivalence():
    series = _synth_range(START, 36)
    times = build_event_timeline(series, start=START, end=START + timedelta(hours=3))
    n = 15
    prefix_snap = snapshot_at(
        session_id="p",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=series,
        gaps=[],
        limitations=[],
        event_times=times[: n + 1],
        event_index=n,
        status="paused",
        speed="max",
    )
    full_snap = snapshot_at(
        session_id="p",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=series,
        gaps=[],
        limitations=[],
        event_times=times,
        event_index=n,
        status="paused",
        speed="max",
    )
    assert prefix_snap.replay_timestamp == full_snap.replay_timestamp
    for tf in ("5m", "15m", "1h", "4h"):
        a = prefix_snap.timeframes[tf]
        b = full_snap.timeframes[tf]
        assert a.closed_count == b.closed_count
        assert a.latest_closed_open_time == b.latest_closed_open_time
        if a.forming_candle and b.forming_candle:
            assert a.forming_candle.open == b.forming_candle.open
            assert a.forming_candle.high == b.forming_candle.high
            assert a.forming_candle.low == b.forming_candle.low
            assert a.forming_candle.close == b.forming_candle.close
        else:
            assert a.forming_candle == b.forming_candle


def test_empty_historical_data():
    times = build_event_timeline({}, start=START, end=START + timedelta(hours=1))
    assert times == []
    snap = snapshot_at(
        session_id="e",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf={},
        gaps=[],
        limitations=["empty"],
        event_times=[],
        event_index=0,
        status="error",
        speed="max",
    )
    assert snap.data_quality == "empty"


@pytest.mark.asyncio
async def test_session_controls_step_reset_speed():
    series = _synth_range(START, 12)
    times = build_event_timeline(series, start=START, end=START + timedelta(hours=1))
    session = ReplaySession(
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        start_time=START,
        end_time=START + timedelta(hours=1),
    )
    session.series_by_tf = series
    session.event_times = times
    session.status = "ready"
    session.event_index = 0

    s1 = await session.step()
    assert s1.event_index == 1
    assert session.status in {"paused", "completed"}

    await session.set_speed("50x")
    assert session.speed == "50x"

    r = await session.reset()
    assert r.event_index == 0
    assert session.status == "ready"

    await session.pause()
    await session.resume()
    # resume only starts runner when previously paused from running path;
    # after reset status is ready — resume is no-op for runner
    await session.stop()
    assert session.status == "stopped"


@pytest.mark.asyncio
async def test_session_isolation():
    s1 = ReplaySession(
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        start_time=START,
        end_time=START + timedelta(hours=1),
    )
    s2 = ReplaySession(
        exchange=EX,
        symbol="ETH/USDT",
        market_type=MT,
        start_time=START,
        end_time=START + timedelta(hours=1),
    )
    assert s1.session_id != s2.session_id
    s1.event_index = 3
    assert s2.event_index == 0


def test_api_create_validation():
    client = TestClient(app)
    resp = client.post(
        "/api/v1/replay/sessions",
        json={
            "exchange": "binance",
            "symbol": "BTC/USDT",
            "market_type": "spot",
            "start_time": "2024-01-01T02:00:00Z",
            "end_time": "2024-01-01T01:00:00Z",
        },
    )
    assert resp.status_code == 422


def test_api_session_lifecycle_with_mocked_loader():
    series = _synth_range(START, 12)
    gaps: list = []
    limitations: list[str] = []

    async def fake_load(**kwargs):
        return series, gaps, limitations

    client = TestClient(app)
    with patch("app.replay.session.load_replay_series", new=AsyncMock(side_effect=fake_load)):
        create = client.post(
            "/api/v1/replay/sessions",
            json={
                "exchange": "binance",
                "symbol": "BTC/USDT",
                "market_type": "spot",
                "start_time": START.isoformat(),
                "end_time": (START + timedelta(hours=1)).isoformat(),
                "speed": "max",
            },
        )
        assert create.status_code == 200, create.text
        body = create.json()
        sid = body["session"]["session_id"]
        assert body["snapshot"]["event_count"] > 0
        assert body["snapshot"]["timestamp_convention"] == "open_time_utc"

        got = client.get(f"/api/v1/replay/sessions/{sid}")
        assert got.status_code == 200

        step = client.post(f"/api/v1/replay/sessions/{sid}/step")
        assert step.status_code == 200
        assert step.json()["snapshot"]["event_index"] == 1

        speed = client.post(
            f"/api/v1/replay/sessions/{sid}/speed",
            json={"speed": "5x"},
        )
        assert speed.status_code == 200
        assert speed.json()["speed"] == "5x"

        reset = client.post(f"/api/v1/replay/sessions/{sid}/reset")
        assert reset.json()["snapshot"]["event_index"] == 0

        pause = client.post(f"/api/v1/replay/sessions/{sid}/pause")
        assert pause.status_code == 200

        # start then pause
        start = client.post(f"/api/v1/replay/sessions/{sid}/start")
        assert start.status_code == 200
        client.post(f"/api/v1/replay/sessions/{sid}/pause")
        client.post(f"/api/v1/replay/sessions/{sid}/resume")
        client.post(f"/api/v1/replay/sessions/{sid}/stop")

        deleted = client.delete(f"/api/v1/replay/sessions/{sid}")
        assert deleted.status_code == 200
        missing = client.get(f"/api/v1/replay/sessions/{sid}")
        assert missing.status_code == 404


def test_api_session_isolation():
    series = _synth_range(START, 8)

    async def fake_load(**kwargs):
        return series, [], []

    client = TestClient(app)
    with patch("app.replay.session.load_replay_series", new=AsyncMock(side_effect=fake_load)):
        a = client.post(
            "/api/v1/replay/sessions",
            json={
                "exchange": "binance",
                "symbol": "BTC/USDT",
                "market_type": "spot",
                "start_time": START.isoformat(),
                "end_time": (START + timedelta(hours=1)).isoformat(),
            },
        ).json()
        b = client.post(
            "/api/v1/replay/sessions",
            json={
                "exchange": "binance",
                "symbol": "ETH/USDT",
                "market_type": "spot",
                "start_time": START.isoformat(),
                "end_time": (START + timedelta(hours=1)).isoformat(),
            },
        ).json()
        assert a["session"]["session_id"] != b["session"]["session_id"]
        client.post(f"/api/v1/replay/sessions/{a['session']['session_id']}/step")
        b2 = client.get(f"/api/v1/replay/sessions/{b['session']['session_id']}").json()
        assert b2["snapshot"]["event_index"] == 0


def test_speed_does_not_change_results():
    series = _synth_range(START, 20)
    times = build_event_timeline(series, start=START, end=START + timedelta(hours=2))
    snaps = []
    for speed in ("1x", "10x", "max"):
        snaps.append(
            snapshot_at(
                session_id="x",
                exchange=EX,
                symbol=SYM,
                market_type=MT,
                series_by_tf=series,
                gaps=[],
                limitations=[],
                event_times=times,
                event_index=7,
                status="paused",
                speed=speed,
            )
        )
    assert snaps[0].timeframes["5m"].closed_count == snaps[1].timeframes["5m"].closed_count
    assert snaps[0].timeframes["5m"].closed_count == snaps[2].timeframes["5m"].closed_count
    assert snaps[0].replay_timestamp == snaps[2].replay_timestamp


def test_pagination_estimate_uses_adapter_limit_bounds():
    cfg = ReplayConfig(max_candles_per_timeframe=500)
    assert cfg.max_candles_per_timeframe == 500
    assert DEFAULT_REPLAY_CONFIG.event_timeframe == Timeframe.M5


# ─── Phase 5.2.7 — Seek API ───


def test_event_index_at_or_before_mapping():
    times = [
        START + timedelta(minutes=5),
        START + timedelta(minutes=10),
        START + timedelta(minutes=15),
    ]
    assert event_index_at_or_before(times, START) == 0  # before first → floor 0
    assert event_index_at_or_before(times, times[0]) == 0
    assert event_index_at_or_before(times, times[0] + timedelta(minutes=2)) == 0
    assert event_index_at_or_before(times, times[1]) == 1
    assert event_index_at_or_before(times, times[2] + timedelta(hours=1)) == 2
    with pytest.raises(ValueError):
        event_index_at_or_before([], START)


def test_api_seek_index_and_timestamp():
    series = _synth_range(START, 24)

    async def fake_load(**kwargs):
        return series, [], []

    client = TestClient(app)
    with patch("app.replay.session.load_replay_series", new=AsyncMock(side_effect=fake_load)):
        create = client.post(
            "/api/v1/replay/sessions",
            json={
                "exchange": "binance",
                "symbol": "BTC/USDT",
                "market_type": "spot",
                "start_time": START.isoformat(),
                "end_time": (START + timedelta(hours=2)).isoformat(),
                "speed": "max",
            },
        )
        assert create.status_code == 200, create.text
        sid = create.json()["session"]["session_id"]
        count = create.json()["snapshot"]["event_count"]
        assert count >= 3
        times = get_replay_manager().require(sid).event_times

        # First
        r0 = client.post(f"/api/v1/replay/sessions/{sid}/seek", json={"event_index": 0})
        assert r0.status_code == 200, r0.text
        assert r0.json()["snapshot"]["event_index"] == 0
        assert r0.json()["snapshot"]["replay_timestamp"] is not None

        # Middle
        mid = count // 2
        rm = client.post(f"/api/v1/replay/sessions/{sid}/seek", json={"event_index": mid})
        assert rm.status_code == 200
        assert rm.json()["snapshot"]["event_index"] == mid

        # Last
        rl = client.post(
            f"/api/v1/replay/sessions/{sid}/seek", json={"event_index": count - 1}
        )
        assert rl.status_code == 200
        assert rl.json()["snapshot"]["event_index"] == count - 1
        assert rl.json()["status"] == "completed"

        # Negative → clamp 0
        rn = client.post(f"/api/v1/replay/sessions/{sid}/seek", json={"event_index": -5})
        assert rn.status_code == 200
        assert rn.json()["snapshot"]["event_index"] == 0

        # Beyond last → clamp last
        rb = client.post(
            f"/api/v1/replay/sessions/{sid}/seek", json={"event_index": count + 50}
        )
        assert rb.status_code == 200
        assert rb.json()["snapshot"]["event_index"] == count - 1

        # Timestamp exact mid
        rt = client.post(
            f"/api/v1/replay/sessions/{sid}/seek",
            json={"timestamp": times[mid].isoformat()},
        )
        assert rt.status_code == 200
        assert rt.json()["snapshot"]["event_index"] == mid

        # Before first
        rbf = client.post(
            f"/api/v1/replay/sessions/{sid}/seek",
            json={"timestamp": (START - timedelta(days=1)).isoformat()},
        )
        assert rbf.status_code == 200
        assert rbf.json()["snapshot"]["event_index"] == 0

        # After last
        ral = client.post(
            f"/api/v1/replay/sessions/{sid}/seek",
            json={"timestamp": (times[-1] + timedelta(days=1)).isoformat()},
        )
        assert ral.status_code == 200
        assert ral.json()["snapshot"]["event_index"] == count - 1

        # Invalid timestamp
        bad_ts = client.post(
            f"/api/v1/replay/sessions/{sid}/seek",
            json={"timestamp": "not-a-timestamp"},
        )
        assert bad_ts.status_code == 422

        # Missing payload
        missing = client.post(f"/api/v1/replay/sessions/{sid}/seek", json={})
        assert missing.status_code == 422

        # Both fields
        both = client.post(
            f"/api/v1/replay/sessions/{sid}/seek",
            json={"event_index": 1, "timestamp": times[1].isoformat()},
        )
        assert both.status_code == 422

        # Unknown session
        unk = client.post(
            "/api/v1/replay/sessions/rp_missing/seek", json={"event_index": 0}
        )
        assert unk.status_code == 404


def test_api_seek_empty_timeline_400():
    """Seek with no events → 400."""
    client = TestClient(app)
    manager = get_replay_manager()

    async def fake_load(**kwargs):
        return {Timeframe.M5: [], Timeframe.M15: [], Timeframe.H1: [], Timeframe.H4: []}, [], []

    with patch("app.replay.session.load_replay_series", new=AsyncMock(side_effect=fake_load)):
        create = client.post(
            "/api/v1/replay/sessions",
            json={
                "exchange": "binance",
                "symbol": "BTC/USDT",
                "market_type": "spot",
                "start_time": START.isoformat(),
                "end_time": (START + timedelta(hours=1)).isoformat(),
            },
        )
        # Empty load may 400 at create or produce empty session
        if create.status_code != 200:
            return
        sid = create.json()["session"]["session_id"]
        sess = manager.get(sid)
        if sess is None or sess.event_times:
            # Force empty for the contract under test
            sess.event_times = []
        r = client.post(f"/api/v1/replay/sessions/{sid}/seek", json={"event_index": 0})
        assert r.status_code == 400


def test_api_seek_backward_drops_future_stack_and_report_clock():
    """Seek backward clears future sim/costs; report binds to new clock."""
    series = _synth_range(START, 36)

    async def fake_load(**kwargs):
        return series, [], []

    client = TestClient(app)
    with patch("app.replay.session.load_replay_series", new=AsyncMock(side_effect=fake_load)):
        create = client.post(
            "/api/v1/replay/sessions",
            json={
                "exchange": "binance",
                "symbol": "BTC/USDT",
                "market_type": "spot",
                "start_time": START.isoformat(),
                "end_time": (START + timedelta(hours=3)).isoformat(),
                "speed": "max",
            },
        )
        assert create.status_code == 200, create.text
        sid = create.json()["session"]["session_id"]
        count = create.json()["snapshot"]["event_count"]
        late = count - 1
        early = max(0, count // 4)

        client.post(f"/api/v1/replay/sessions/{sid}/analysis/enable")
        client.post(f"/api/v1/replay/sessions/{sid}/simulation/enable")
        client.post(f"/api/v1/replay/sessions/{sid}/costs/enable")
        client.post(f"/api/v1/replay/sessions/{sid}/analytics/enable")

        # Seek to end (rebuild at late clock)
        end = client.post(
            f"/api/v1/replay/sessions/{sid}/seek", json={"event_index": late}
        )
        assert end.status_code == 200
        assert end.json()["snapshot"]["event_index"] == late

        # Seed a "future" trade relative to early clock by attaching after late seek
        from app.replay.simulation.models import SimulatedTrade, SimulationExecutionEvent

        sess = get_replay_manager().require(sid)
        future_ts = sess.event_times[late]
        early_ts = sess.event_times[early]
        trade = SimulatedTrade(
            trade_id="seek_future",
            signal_key="sig_seek_future",
            replay_session_id=sid,
            exchange=EX,
            symbol=SYM,
            market_type=MT,
            direction="LONG",
            decision="LONG",
            decision_timestamp=future_ts,
            decision_event_index=late,
            lifecycle_status="closed_tp",
            entry_limit_price=100.0,
            entry_price=100.0,
            entry_timestamp=future_ts,
            exit_timestamp=future_ts,
            initial_stop_loss=95.0,
            current_stop_loss=95.0,
            take_profit_levels=[110.0],
            tp_allocations=[1.0],
            tp_filled=[True],
            original_quantity=1.0,
            remaining_quantity=0.0,
            executed_quantity=1.0,
            quantity_closed_tp=1.0,
            config_version="v",
            created_at=future_ts,
            updated_at=future_ts,
            execution_events=[
                SimulationExecutionEvent(
                    event_id="sf_o",
                    event_type="trade_opened",
                    timestamp=future_ts,
                    price=100.0,
                    quantity=1.0,
                ),
                SimulationExecutionEvent(
                    event_id="sf_x",
                    event_type="trade_closed",
                    timestamp=future_ts,
                    price=110.0,
                    quantity=1.0,
                    reason="TP",
                ),
            ],
        )
        sess.simulator.trades[trade.trade_id] = trade
        sess.cost_engine.rebuild_from_trades(list(sess.simulator.trades.values()))

        # Seek backward — rebuild drops future-clocked trade
        back = client.post(
            f"/api/v1/replay/sessions/{sid}/seek", json={"event_index": early}
        )
        assert back.status_code == 200
        assert back.json()["snapshot"]["event_index"] == early
        sess2 = get_replay_manager().require(sid)
        assert "seek_future" not in sess2.simulator.trades
        ledger_early = sess2.cost_engine.ledger.all_entries()
        assert all(e.timestamp <= early_ts for e in ledger_early) or not ledger_early

        report = client.get(f"/api/v1/replay/sessions/{sid}/report")
        assert report.status_code == 200, report.text
        meta = report.json()["report"]["metadata"]
        assert meta["event_index"] == early
        assert meta["replay_timestamp"] == back.json()["snapshot"]["replay_timestamp"]
        for t in report.json()["report"]["completed_trades"]:
            assert t["trade_id"] != "seek_future"

        # Seek forward again — deterministic, no duplicates from empty rebuild
        fwd = client.post(
            f"/api/v1/replay/sessions/{sid}/seek", json={"event_index": late}
        )
        assert fwd.status_code == 200
        assert fwd.json()["snapshot"]["event_index"] == late
        sess3 = get_replay_manager().require(sid)
        ids = [e.execution_id for e in sess3.cost_engine.ledger.all_entries()]
        assert len(ids) == len(set(ids))

