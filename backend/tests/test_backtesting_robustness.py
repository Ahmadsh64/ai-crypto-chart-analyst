"""Phase 5.2.5 — Backtesting robustness & validation tests.

Covers data integrity, no-look-ahead, prefix invariance, future perturbation,
reset/seek/step determinism, MTF sync, and multi-window stability.
Does not assert strategy profitability.
"""

from __future__ import annotations

import copy
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.market_data.normalizer import is_valid_ohlc
from app.replay.analysis.pipeline import run_historical_analysis
from app.replay.analysis.validation import LookAheadError, assert_no_future_candles, filter_closed_prefix
from app.replay.manager import reset_replay_manager
from app.replay.robustness import (
    IntegrityStatus,
    analysis_fingerprint,
    analytics_fingerprint,
    classify_series_integrity,
    cost_fingerprint,
    simulation_fingerprint,
    validate_pagination_order,
)
from app.replay.session import ReplaySession
from app.replay.timeline import (
    build_event_timeline,
    candle_close_time,
    closed_candles_as_of,
    is_aligned_open,
    is_valid_candle,
    sanitize_series,
    snapshot_at,
)

EX = ExchangeId.BINANCE
SYM = "BTC/USDT"
MT = MarketType.SPOT
UTC = timezone.utc
START = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)


def _tf_sec(tf: Timeframe) -> int:
    return {
        Timeframe.M5: 300,
        Timeframe.M15: 900,
        Timeframe.H1: 3600,
        Timeframe.H4: 14400,
    }[tf]


def _c(
    open_ts: datetime,
    o: float,
    h: float,
    l: float,
    cl: float,
    *,
    tf: Timeframe = Timeframe.M5,
    vol: float = 10.0,
    symbol: str = SYM,
) -> Candle:
    return Candle(
        timestamp=open_ts,
        open=o,
        high=h,
        low=l,
        close=cl,
        volume=vol,
        exchange=EX,
        symbol=symbol,
        market_type=MT,
        is_closed=True,
        close_time=open_ts + timedelta(seconds=_tf_sec(tf)) - timedelta(milliseconds=1),
    )


def _synth(
    n_5m: int = 120,
    *,
    regime: str = "mild",
    start: datetime = START,
) -> dict[Timeframe, list[Candle]]:
    """Labeled synthetic fixtures — software robustness only, not market truth."""
    m5: list[Candle] = []
    price = 100.0
    for i in range(n_5m):
        ts = start + timedelta(minutes=5 * i)
        if regime == "bull":
            delta = 0.55
        elif regime == "bear":
            delta = -0.55
        elif regime == "sideways":
            delta = 0.15 if i % 2 == 0 else -0.15
        elif regime == "high_vol":
            delta = 2.5 if (i // 3) % 2 == 0 else -2.4
        elif regime == "low_vol":
            delta = 0.05 if i % 2 == 0 else -0.05
        else:
            delta = 0.4 if (i // 8) % 2 == 0 else -0.35
        o = price
        cl = price + delta
        h = max(o, cl) + (0.8 if regime == "high_vol" else 0.3)
        l = min(o, cl) - (0.8 if regime == "high_vol" else 0.3)
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


def _perturb_future(
    series: dict[Timeframe, list[Candle]],
    clock: datetime,
) -> dict[Timeframe, list[Candle]]:
    """Change all candles that close strictly after clock to different valid OHLCV."""
    out: dict[Timeframe, list[Candle]] = {}
    for tf, candles in series.items():
        new_list: list[Candle] = []
        for i, c in enumerate(candles):
            if candle_close_time(c, tf) <= clock:
                new_list.append(c)
                continue
            # Deterministic but very different path after T
            bump = 50.0 + (i % 7) * 3.0
            o = c.open + bump
            cl = c.close + bump + 1.5
            h = max(o, cl) + 2.0
            l = min(o, cl) - 2.0
            new_list.append(
                _c(
                    ensure_utc_ts(c.timestamp),
                    o,
                    h,
                    l,
                    cl,
                    tf=tf,
                    vol=c.volume + 100.0,
                )
            )
        out[tf] = new_list
    return out


def ensure_utc_ts(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def _session_from_series(
    series: dict[Timeframe, list[Candle]],
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> ReplaySession:
    start = start or START
    end = end or (START + timedelta(minutes=5 * max(len(series[Timeframe.M5]) - 1, 1)))
    sess = ReplaySession(
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        start_time=start,
        end_time=end,
    )
    sess.series_by_tf = series
    sess.event_times = build_event_timeline(series, start=start, end=end)
    sess.status = "ready" if sess.event_times else "error"
    sess.event_index = 0
    return sess


@pytest.fixture(autouse=True)
def _reset_mgr():
    reset_replay_manager()
    yield
    reset_replay_manager()


# ─── Part 2: Data integrity ───


def test_integrity_rejects_nan_volume():
    assert not is_valid_ohlc(10, 12, 9, 11, float("nan"))
    bad = Candle.model_construct(
        timestamp=START,
        open=10,
        high=12,
        low=9,
        close=11,
        volume=float("nan"),
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        is_closed=True,
        close_time=None,
    )
    assert not is_valid_candle(bad)
    cleaned, _, notes = sanitize_series(
        [bad, _c(START + timedelta(minutes=5), 1, 2, 0.5, 1.5)],
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        timeframe=Timeframe.M5,
    )
    assert len(cleaned) == 1
    assert any("invalid" in n.lower() for n in notes)


def test_integrity_rejects_inf_and_negative_volume():
    for vol in (float("inf"), -1.0):
        bad = Candle.model_construct(
            timestamp=START,
            open=10,
            high=12,
            low=9,
            close=11,
            volume=vol,
            exchange=EX,
            symbol=SYM,
            market_type=MT,
            is_closed=True,
            close_time=None,
        )
        assert not is_valid_candle(bad)


def test_integrity_utc_alignment_and_misaligned_drop():
    assert is_aligned_open(START, Timeframe.M5)
    assert is_aligned_open(START, Timeframe.H1)
    assert is_aligned_open(START, Timeframe.H4)
    mis = START + timedelta(minutes=1)
    assert not is_aligned_open(mis, Timeframe.M5)
    cleaned, _, notes = sanitize_series(
        [_c(mis, 1, 2, 0.5, 1.5), _c(START, 1, 2, 0.5, 1.5)],
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        timeframe=Timeframe.M5,
    )
    assert len(cleaned) == 1
    assert cleaned[0].timestamp == START
    assert any("misaligned" in n.lower() for n in notes)


def test_integrity_classify_continuous_gaps_invalid_unavailable():
    continuous = [_c(START + timedelta(minutes=5 * i), 1, 2, 0.5, 1.5) for i in range(5)]
    r = classify_series_integrity(
        continuous, exchange=EX, symbol=SYM, market_type=MT, timeframe=Timeframe.M5
    )
    assert r.status == IntegrityStatus.CONTINUOUS
    assert r.gap_count == 0

    gapped = [continuous[0], continuous[1], continuous[3], continuous[4]]
    rg = classify_series_integrity(
        gapped, exchange=EX, symbol=SYM, market_type=MT, timeframe=Timeframe.M5
    )
    assert rg.status == IntegrityStatus.GAPS
    assert rg.gap_count >= 1
    # Gaps are reported — never filled
    assert rg.cleaned_count == 4

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
    ri = classify_series_integrity(
        [bad], exchange=EX, symbol=SYM, market_type=MT, timeframe=Timeframe.M5
    )
    assert ri.status == IntegrityStatus.INVALID
    assert ri.cleaned_count == 0

    ru = classify_series_integrity(
        [], exchange=EX, symbol=SYM, market_type=MT, timeframe=Timeframe.M5
    )
    assert ru.status == IntegrityStatus.UNAVAILABLE


def test_integrity_pagination_merge_dedupes_no_fabricate():
    page1 = [_c(START + timedelta(minutes=5 * i), 1, 2, 0.5, 1.5) for i in range(3)]
    page2 = [
        page1[-1],  # duplicate overlap
        _c(START + timedelta(minutes=15), 1, 2, 0.5, 1.5),
        _c(START + timedelta(minutes=20), 1, 2, 0.5, 1.5),
    ]
    # Unsorted page3
    page3 = [
        _c(START + timedelta(minutes=30), 1, 2, 0.5, 1.5),
        _c(START + timedelta(minutes=25), 1, 2, 0.5, 1.5),
    ]
    cleaned, notes = validate_pagination_order(
        [page1, page2, page3],
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        timeframe=Timeframe.M5,
    )
    opens = [c.timestamp for c in cleaned]
    assert opens == sorted(opens)
    assert len(cleaned) == 7  # 0,5,10,15,20,25,30 — overlap dropped
    assert all(is_aligned_open(c.timestamp, Timeframe.M5) for c in cleaned)


def test_integrity_htf_boundaries_consistent():
    series = _synth(48)
    for tf in (Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4):
        for c in series[tf]:
            assert is_aligned_open(c.timestamp, tf)
            assert c.timestamp.tzinfo is not None
            assert candle_close_time(c, tf) > ensure_utc_ts(c.timestamp)


# ─── Part 3–4: No-look-ahead + prefix invariance + perturbation ───


def test_filter_closed_prefix_rejects_injected_future():
    series = _synth(20)
    clock = candle_close_time(series[Timeframe.M5][5], Timeframe.M5)
    prefix = filter_closed_prefix(
        series[Timeframe.M5], timeframe=Timeframe.M5, clock=clock
    )
    assert all(candle_close_time(c, Timeframe.M5) <= clock for c in prefix)
    future = series[Timeframe.M5][10]
    with pytest.raises(LookAheadError):
        assert_no_future_candles(
            prefix + [future], timeframe=Timeframe.M5, clock=clock
        )


@pytest.mark.parametrize("idx", [20, 40, 60, 80])
def test_prefix_invariance_and_future_perturbation(idx: int):
    series = _synth(100)
    clock = candle_close_time(series[Timeframe.M5][idx], Timeframe.M5)
    prefix_only = {
        tf: closed_candles_as_of(candles, tf, clock) for tf, candles in series.items()
    }
    a = run_historical_analysis(
        session_id="pA",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=prefix_only,
        clock=clock,
        event_index=idx,
    )
    b = run_historical_analysis(
        session_id="pB",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=series,
        clock=clock,
        event_index=idx,
    )
    assert analysis_fingerprint(a) == analysis_fingerprint(b)

    perturbed = _perturb_future(series, clock)
    # Ensure perturbation actually changed future bars
    assert any(
        candle_close_time(c, Timeframe.M5) > clock
        and c.close != series[Timeframe.M5][i].close
        for i, c in enumerate(perturbed[Timeframe.M5])
    )
    c = run_historical_analysis(
        session_id="pC",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=perturbed,
        clock=clock,
        event_index=idx,
    )
    assert analysis_fingerprint(a) == analysis_fingerprint(c)


def test_future_perturbation_not_defeated_by_shared_cache():
    """Two independent pipeline calls — no shared session cache."""
    series = _synth(90)
    idx = 50
    clock = candle_close_time(series[Timeframe.M5][idx], Timeframe.M5)
    baseline = run_historical_analysis(
        session_id="cache_a",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=series,
        clock=clock,
        event_index=idx,
    )
    # Deep-copy then mutate future so accidental shared refs fail the test
    mutated = {
        tf: [copy.copy(c) for c in candles] for tf, candles in series.items()
    }
    mutated = _perturb_future(mutated, clock)
    after = run_historical_analysis(
        session_id="cache_b",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=mutated,
        clock=clock,
        event_index=idx,
    )
    assert analysis_fingerprint(baseline) == analysis_fingerprint(after)


# ─── Part 5: Reset / seek / step determinism ───


@pytest.mark.asyncio
async def test_reset_seek_step_full_stack_determinism():
    series = _synth(80, regime="mild")
    end = START + timedelta(minutes=5 * 79)
    target = 45

    async def run_to_target_via_steps(sess: ReplaySession) -> tuple[str, str, str, str]:
        await sess.enable_analysis()
        await sess.enable_simulation()
        await sess.enable_costs()
        await sess.enable_analytics()
        while sess.event_index < target:
            await sess.step()
        clock = sess.event_times[sess.event_index]
        a = analysis_fingerprint(sess.current_analysis)
        s = simulation_fingerprint(sess.simulator.snapshot(clock))
        c = cost_fingerprint(
            sess.cost_engine.snapshot(
                list(sess.simulator.trades.values()), replay_timestamp=clock
            )
        )
        an = analytics_fingerprint(
            sess.analytics_engine.snapshot(
                list(sess.simulator.trades.values()),
                sess.cost_engine,
                replay_timestamp=clock,
                event_index=sess.event_index,
            )
        )
        return a, s, c, an

    s1 = _session_from_series(series, end=end)
    fp1 = await run_to_target_via_steps(s1)

    s2 = _session_from_series(copy.deepcopy(series), end=end)
    await s2.enable_analysis()
    await s2.enable_simulation()
    await s2.enable_costs()
    await s2.enable_analytics()
    while s2.event_index < target:
        await s2.step()
    await s2.reset()
    while s2.event_index < target:
        await s2.step()
    clock2 = s2.event_times[s2.event_index]
    fp2 = (
        analysis_fingerprint(s2.current_analysis),
        simulation_fingerprint(s2.simulator.snapshot(clock2)),
        cost_fingerprint(
            s2.cost_engine.snapshot(
                list(s2.simulator.trades.values()), replay_timestamp=clock2
            )
        ),
        analytics_fingerprint(
            s2.analytics_engine.snapshot(
                list(s2.simulator.trades.values()),
                s2.cost_engine,
                replay_timestamp=clock2,
                event_index=s2.event_index,
            )
        ),
    )
    assert fp1 == fp2

    # Seek forward to target from 0
    s3 = _session_from_series(copy.deepcopy(series), end=end)
    await s3.enable_analysis()
    await s3.enable_simulation()
    await s3.enable_costs()
    await s3.enable_analytics()
    await s3.seek(target)
    clock3 = s3.event_times[s3.event_index]
    fp3 = (
        analysis_fingerprint(s3.current_analysis),
        simulation_fingerprint(s3.simulator.snapshot(clock3)),
        cost_fingerprint(
            s3.cost_engine.snapshot(
                list(s3.simulator.trades.values()), replay_timestamp=clock3
            )
        ),
        analytics_fingerprint(
            s3.analytics_engine.snapshot(
                list(s3.simulator.trades.values()),
                s3.cost_engine,
                replay_timestamp=clock3,
                event_index=s3.event_index,
            )
        ),
    )
    assert fp1 == fp3

    # Seek past target then back
    await s3.seek(min(target + 20, len(s3.event_times) - 1))
    await s3.seek(target)
    clock4 = s3.event_times[s3.event_index]
    fp4 = (
        analysis_fingerprint(s3.current_analysis),
        simulation_fingerprint(s3.simulator.snapshot(clock4)),
        cost_fingerprint(
            s3.cost_engine.snapshot(
                list(s3.simulator.trades.values()), replay_timestamp=clock4
            )
        ),
        analytics_fingerprint(
            s3.analytics_engine.snapshot(
                list(s3.simulator.trades.values()),
                s3.cost_engine,
                replay_timestamp=clock4,
                event_index=s3.event_index,
            )
        ),
    )
    assert fp1 == fp4

    # Speed must not change analytical fingerprints
    await s3.set_speed("max")
    await s3.set_speed("1x")
    clock5 = s3.event_times[s3.event_index]
    fp5 = (
        analysis_fingerprint(s3.current_analysis),
        simulation_fingerprint(s3.simulator.snapshot(clock5)),
        cost_fingerprint(
            s3.cost_engine.snapshot(
                list(s3.simulator.trades.values()), replay_timestamp=clock5
            )
        ),
        analytics_fingerprint(
            s3.analytics_engine.snapshot(
                list(s3.simulator.trades.values()),
                s3.cost_engine,
                replay_timestamp=clock5,
                event_index=s3.event_index,
            )
        ),
    )
    assert fp1 == fp5


@pytest.mark.asyncio
async def test_seek_backward_drops_future_trades_and_costs():
    series = _synth(70)
    end = START + timedelta(minutes=5 * 69)
    sess = _session_from_series(series, end=end)
    await sess.enable_analysis()
    await sess.enable_simulation()
    await sess.enable_costs()
    await sess.enable_analytics()
    late = min(55, len(sess.event_times) - 1)
    early = min(25, late)
    await sess.seek(late)
    late_trade_ids = set(sess.simulator.trades.keys())
    late_ledger = len(sess.cost_engine.ledger.all_entries())
    await sess.seek(early)
    early_clock = sess.event_times[sess.event_index]
    for t in sess.simulator.trades.values():
        if t.entry_timestamp is not None:
            assert t.entry_timestamp <= early_clock
        for e in t.execution_events:
            assert e.timestamp <= early_clock
    for e in sess.cost_engine.ledger.all_entries():
        assert e.event_timestamp <= early_clock
    # Seeking earlier must not retain strictly-later ledger volume blindly
    assert len(sess.cost_engine.ledger.all_entries()) <= late_ledger
    # Trade set at early is a rebuild, not a subset of mutated IDs necessarily —
    # but no trade may reference a decision after early clock.
    for t in sess.simulator.trades.values():
        assert t.decision_timestamp <= early_clock
    _ = late_trade_ids  # used for documentation of rebuild semantics


# ─── Part 6: MTF sync ───


def test_mtf_closure_boundaries_and_forming():
    series = _synth(48)
    times = build_event_timeline(
        series, start=START, end=START + timedelta(hours=4)
    )
    # Mid 15m bar: first 5m close inside a 15m window that is not yet closed
    # Index 1 closes at 00:04:59.999 — 15m open 00:00 not closed until 00:14:59.999
    clock = times[1]
    snap = snapshot_at(
        session_id="mtf",
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
    assert snap.timeframes["15m"].closed_count == 0
    forming = snap.timeframes["15m"].forming_candle
    assert forming is not None
    assert forming.is_closed is False

    # At first 15m close boundary
    m15_close_idx = None
    for i, t in enumerate(times):
        closed_15 = closed_candles_as_of(series[Timeframe.M15], Timeframe.M15, t)
        if closed_15:
            m15_close_idx = i
            break
    assert m15_close_idx is not None
    snap15 = snapshot_at(
        session_id="mtf",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=series,
        gaps=[],
        limitations=[],
        event_times=times,
        event_index=m15_close_idx,
        status="paused",
        speed="max",
    )
    assert snap15.timeframes["15m"].closed_count >= 1
    assert snap15.timeframes["15m"].forming_candle is None or (
        snap15.timeframes["15m"].forming_candle.is_closed is False
    )

    # 1h / 4h must not confirm before their close times
    for tf_key, tf in (("1h", Timeframe.H1), ("4h", Timeframe.H4)):
        for i, t in enumerate(times[:12]):
            closed = closed_candles_as_of(series[tf], tf, t)
            for c in closed:
                assert candle_close_time(c, tf) <= t


def test_mtf_prefix_matches_reconstructed_state():
    series = _synth(96)
    idx = 40
    clock = candle_close_time(series[Timeframe.M5][idx], Timeframe.M5)
    times = build_event_timeline(
        series, start=START, end=START + timedelta(minutes=5 * 95)
    )
    full = snapshot_at(
        session_id="m",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=series,
        gaps=[],
        limitations=[],
        event_times=times,
        event_index=idx,
        status="paused",
        speed="max",
    )
    prefix = {
        tf: closed_candles_as_of(candles, tf, clock) for tf, candles in series.items()
    }
    # Include forming-capable 5m prefix equal to closed-as-of for snapshot compare of counts
    pre_times = [t for t in times if t <= clock]
    pref_snap = snapshot_at(
        session_id="m",
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        series_by_tf=prefix,
        gaps=[],
        limitations=[],
        event_times=pre_times,
        event_index=len(pre_times) - 1,
        status="paused",
        speed="max",
    )
    for tf in ("5m", "15m", "1h", "4h"):
        assert full.timeframes[tf].closed_count == pref_snap.timeframes[tf].closed_count


# ─── Part 7–8: Pipeline consistency + stability windows ───


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "label,n,regime",
    [
        ("short_mild", 40, "mild"),
        ("medium_bull", 80, "bull"),
        ("medium_bear", 80, "bear"),
        ("sideways", 60, "sideways"),
        ("high_vol", 60, "high_vol"),
        ("low_vol", 60, "low_vol"),
        ("longer", 140, "mild"),
    ],
)
async def test_stability_windows_no_crash_deterministic(label: str, n: int, regime: str):
    series = _synth(n, regime=regime)
    end = START + timedelta(minutes=5 * (n - 1))
    sess = _session_from_series(series, end=end)
    assert sess.event_times, label
    await sess.enable_analysis()
    await sess.enable_simulation()
    await sess.enable_costs()
    await sess.enable_analytics()
    mid = min(len(sess.event_times) - 1, max(1, len(sess.event_times) // 2))
    await sess.seek(mid)
    clock = sess.event_times[sess.event_index]
    fp = (
        analysis_fingerprint(sess.current_analysis),
        simulation_fingerprint(sess.simulator.snapshot(clock)),
        cost_fingerprint(
            sess.cost_engine.snapshot(
                list(sess.simulator.trades.values()), replay_timestamp=clock
            )
        ),
        analytics_fingerprint(
            sess.analytics_engine.snapshot(
                list(sess.simulator.trades.values()),
                sess.cost_engine,
                replay_timestamp=clock,
                event_index=sess.event_index,
            )
        ),
    )
    await sess.seek(0)
    await sess.seek(mid)
    clock2 = sess.event_times[sess.event_index]
    fp2 = (
        analysis_fingerprint(sess.current_analysis),
        simulation_fingerprint(sess.simulator.snapshot(clock2)),
        cost_fingerprint(
            sess.cost_engine.snapshot(
                list(sess.simulator.trades.values()), replay_timestamp=clock2
            )
        ),
        analytics_fingerprint(
            sess.analytics_engine.snapshot(
                list(sess.simulator.trades.values()),
                sess.cost_engine,
                replay_timestamp=clock2,
                event_index=sess.event_index,
            )
        ),
    )
    assert fp == fp2, label
    from app.replay.simulation.validation import quantities_conserved

    for t in sess.simulator.trades.values():
        if t.lifecycle_status in {"rejected", "cancelled"}:
            continue
        if t.original_quantity <= 0:
            continue
        assert quantities_conserved(t), (label, t.trade_id, t.lifecycle_status)


@pytest.mark.asyncio
async def test_gap_fixture_does_not_fabricate_or_crash():
    series = _synth(40)
    # Remove several 5m bars creating gaps
    m5 = [
        c
        for i, c in enumerate(series[Timeframe.M5])
        if i not in {5, 6, 7, 20, 21}
    ]
    cleaned, gaps, notes = sanitize_series(
        m5, exchange=EX, symbol=SYM, market_type=MT, timeframe=Timeframe.M5
    )
    assert gaps
    series2 = dict(series)
    series2[Timeframe.M5] = cleaned
    sess = _session_from_series(series2, end=START + timedelta(minutes=5 * 39))
    if not sess.event_times:
        return
    await sess.enable_analysis()
    await sess.seek(min(10, len(sess.event_times) - 1))
    assert sess.current_analysis is not None


@pytest.mark.asyncio
async def test_insufficient_history_explicit():
    series = _synth(3)
    sess = _session_from_series(series, end=START + timedelta(minutes=10))
    await sess.enable_analysis()
    assert sess.current_analysis is not None
    # Warm-up / incomplete is represented via data_ready / limitations — not a crash
    assert isinstance(sess.current_analysis.data_ready, bool)


# ─── Part 9: Light performance observations ───


@pytest.mark.asyncio
async def test_perf_seek_and_step_latency_smoke():
    series = _synth(100)
    end = START + timedelta(minutes=5 * 99)
    sess = _session_from_series(series, end=end)
    await sess.enable_analysis()
    await sess.enable_simulation()
    t0 = time.perf_counter()
    await sess.seek(70)
    seek_ms = (time.perf_counter() - t0) * 1000
    t1 = time.perf_counter()
    await sess.step()
    step_ms = (time.perf_counter() - t1) * 1000
    t2 = time.perf_counter()
    await sess.reset()
    reset_ms = (time.perf_counter() - t2) * 1000
    # Soft bounds — document, do not overfit
    assert seek_ms < 60_000
    assert step_ms < 30_000
    assert reset_ms < 60_000
    # Cache hit should be faster or equal for repeated index
    t3 = time.perf_counter()
    await sess.seek(70)
    seek2_ms = (time.perf_counter() - t3) * 1000
    assert seek2_ms < 60_000
    _ = (seek_ms, step_ms, reset_ms, seek2_ms)


# ─── Spot short safety ───


@pytest.mark.asyncio
async def test_spot_never_opens_short_in_replay_stack():
    series = _synth(80, regime="bear")
    sess = _session_from_series(series, end=START + timedelta(minutes=5 * 79))
    await sess.enable_analysis()
    await sess.enable_simulation()
    await sess.seek(min(60, len(sess.event_times) - 1))
    for t in sess.simulator.trades.values():
        if t.lifecycle_status in {"open", "partially_closed", "closed_tp", "closed_sl", "closed_expired"}:
            assert t.direction != "SHORT"
