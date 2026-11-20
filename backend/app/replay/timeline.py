"""Deterministic multi-TF timeline with no-look-ahead (Phase 5.1).

Candle ``timestamp`` is the **open** time (UTC). A candle is closed at replay
clock ``T`` iff ``close_time <= T``, where
``close_time = open + timeframe_seconds - 1ms`` (or API-provided close_time).
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import datetime, timedelta, timezone

from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.market_data.candles import timeframe_to_seconds
from app.replay.config import DEFAULT_REPLAY_CONFIG, REPLAY_TIMEFRAMES, ReplayConfig
from app.replay.models import CandleGapInfo, ReplaySnapshot, TimeframeReplayState


def ensure_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def event_index_at_or_before(
    event_times: list[datetime],
    timestamp: datetime,
) -> int:
    """Map a UTC timestamp to the latest event index with event_time <= timestamp.

    Phase 5.2.7 seek contract:
    - Never selects a future event.
    - Timestamp before the first event → index 0 (same floor as negative index clamp).
    - Timestamp after the last event → last index.
    - Empty timeline → ValueError (caller maps to HTTP 400).
    """
    if not event_times:
        raise ValueError("No events loaded.")
    ts = ensure_utc(timestamp)
    times = [ensure_utc(t) for t in event_times]
    # bisect_right → first index with time > ts; step back one for <= ts.
    i = bisect_right(times, ts) - 1
    if i < 0:
        return 0
    return i


def candle_close_time(candle: Candle, timeframe: Timeframe) -> datetime:
    if candle.close_time is not None:
        return ensure_utc(candle.close_time)
    open_ts = ensure_utc(candle.timestamp)
    return open_ts + timedelta(seconds=timeframe_to_seconds(timeframe)) - timedelta(
        milliseconds=1
    )


def build_event_timeline(
    series_by_tf: dict[Timeframe, list[Candle]],
    *,
    start: datetime,
    end: datetime,
    config: ReplayConfig | None = None,
) -> list[datetime]:
    """Event clock ticks = closed 5M (event TF) close times within [start, end]."""
    cfg = config or DEFAULT_REPLAY_CONFIG
    start = ensure_utc(start)
    end = ensure_utc(end)
    event_tf = cfg.event_timeframe
    base = series_by_tf.get(event_tf, [])
    times: list[datetime] = []
    for c in base:
        ct = candle_close_time(c, event_tf)
        if start <= ct <= end:
            times.append(ct)
    # Deduplicate while preserving order
    out: list[datetime] = []
    seen: set[datetime] = set()
    for t in sorted(times):
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def snapshot_at(
    *,
    session_id: str,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    series_by_tf: dict[Timeframe, list[Candle]],
    gaps: list[CandleGapInfo],
    limitations: list[str],
    event_times: list[datetime],
    event_index: int,
    status: str,
    speed: str,
    config: ReplayConfig | None = None,
) -> ReplaySnapshot:
    cfg = config or DEFAULT_REPLAY_CONFIG
    if not event_times:
        clock = ensure_utc(datetime.now(timezone.utc))
        idx = 0
    else:
        idx = max(0, min(event_index, len(event_times) - 1))
        clock = event_times[idx]

    base_5m = series_by_tf.get(Timeframe.M5, [])
    closed_5m = [c for c in base_5m if candle_close_time(c, Timeframe.M5) <= clock]

    tf_states: dict[str, TimeframeReplayState] = {}
    for tf in cfg.timeframes:
        series = series_by_tf.get(tf, [])
        closed = [c for c in series if candle_close_time(c, tf) <= clock]
        forming = _forming_candle(
            tf=tf,
            series=series,
            closed_5m=closed_5m,
            clock=clock,
            exchange=exchange,
            symbol=symbol,
            market_type=market_type,
        )
        preview = closed[-cfg.preview_closed_limit :] if closed else []
        quality: str = "empty"
        if closed:
            quality = "ok"
            if any(g.timeframe == tf for g in gaps):
                quality = "gaps"
        elif series:
            quality = "insufficient"

        latest_closed = closed[-1] if closed else None
        latest_price = None
        if forming is not None:
            latest_price = forming.close
        elif latest_closed is not None:
            latest_price = latest_closed.close

        tf_states[tf.value] = TimeframeReplayState(
            timeframe=tf,
            closed_candles=preview,
            closed_count=len(closed),
            forming_candle=forming,
            latest_closed_open_time=(
                ensure_utc(latest_closed.timestamp) if latest_closed else None
            ),
            latest_closed_close_time=(
                candle_close_time(latest_closed, tf) if latest_closed else None
            ),
            latest_price=latest_price,
            is_ready=len(closed) >= 1,
            data_quality=quality,  # type: ignore[arg-type]
            gap_count=sum(1 for g in gaps if g.timeframe == tf),
        )

    overall = "ok"
    if not event_times:
        overall = "empty"
    elif any(s.data_quality == "empty" for s in tf_states.values()):
        overall = "partial"
    elif any(s.data_quality in {"gaps", "insufficient"} for s in tf_states.values()):
        overall = "partial"

    progress = 0.0
    if event_times:
        progress = round((idx + 1) / len(event_times) * 100.0, 4)

    return ReplaySnapshot(
        session_id=session_id,
        replay_timestamp=clock,
        exchange=exchange,
        symbol=symbol.upper(),
        market_type=market_type,
        event_index=idx,
        event_count=len(event_times),
        progress_pct=progress,
        status=status,  # type: ignore[arg-type]
        speed=speed,  # type: ignore[arg-type]
        timeframes=tf_states,
        gaps=gaps,
        data_quality=overall,  # type: ignore[arg-type]
        limitations=list(dict.fromkeys(limitations)),
        config_version=cfg.config_version,
    )


def closed_candles_as_of(
    series: list[Candle],
    timeframe: Timeframe,
    clock: datetime,
) -> list[Candle]:
    clock = ensure_utc(clock)
    return [c for c in series if candle_close_time(c, timeframe) <= clock]


def _forming_candle(
    *,
    tf: Timeframe,
    series: list[Candle],
    closed_5m: list[Candle],
    clock: datetime,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
) -> Candle | None:
    """Build forming HTF/LTF candle from closed 5M only — never use future OHLC."""
    clock = ensure_utc(clock)
    step = timedelta(seconds=timeframe_to_seconds(tf))
    # Floor clock to TF open
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    seconds = int((clock - epoch).total_seconds())
    tf_sec = timeframe_to_seconds(tf)
    open_sec = (seconds // tf_sec) * tf_sec
    open_ts = epoch + timedelta(seconds=open_sec)
    close_ts = open_ts + step - timedelta(milliseconds=1)
    if clock >= close_ts:
        # At exact close, candle is closed — no forming
        return None

    # Collect closed 5m bars inside [open_ts, clock]
    parts = [
        c
        for c in closed_5m
        if ensure_utc(c.timestamp) >= open_ts
        and candle_close_time(c, Timeframe.M5) <= clock
    ]
    if not parts:
        # No confirmed lower-TF data yet inside this bar — do not invent OHLC.
        return None

    o = parts[0].open
    h = max(c.high for c in parts)
    l = min(c.low for c in parts)
    cl = parts[-1].close
    vol = sum(c.volume for c in parts)
    _ = series  # series kept for call-site symmetry; forming uses closed_5m only

    return Candle(
        timestamp=open_ts,
        open=o,
        high=h,
        low=l,
        close=cl,
        volume=vol,
        exchange=exchange,
        symbol=symbol.upper(),
        market_type=market_type,
        is_closed=False,
        close_time=close_ts,
    )


def _finite(v: float) -> bool:
    return v == v and abs(v) != float("inf")


def is_valid_candle(c: Candle) -> bool:
    """Reject invalid OHLC and non-finite / negative volume. No fabrication."""
    if c.high < c.low:
        return False
    if c.high < max(c.open, c.close):
        return False
    if c.low > min(c.open, c.close):
        return False
    vals = (c.open, c.high, c.low, c.close, c.volume)
    if not all(_finite(v) for v in vals):
        return False
    if c.volume < 0:
        return False
    return True


# Back-compat alias used inside sanitize_series.
_valid_ohlc = is_valid_candle


def is_aligned_open(ts: datetime, timeframe: Timeframe) -> bool:
    """True when open timestamp is UTC-aligned to the timeframe boundary."""
    ts = ensure_utc(ts)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    step = timeframe_to_seconds(timeframe)
    seconds = int((ts - epoch).total_seconds())
    return seconds % step == 0 and ts.microsecond == 0


def sanitize_series(
    candles: list[Candle],
    *,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    timeframe: Timeframe,
) -> tuple[list[Candle], list[CandleGapInfo], list[str]]:
    """Sort, dedupe by open time, validate OHLC, detect gaps. No fabrication."""
    limitations: list[str] = []
    gaps: list[CandleGapInfo] = []
    by_open: dict[datetime, Candle] = {}
    misaligned = 0
    for c in candles:
        if c.exchange != exchange or c.market_type != market_type:
            continue
        if c.symbol.upper() != symbol.upper():
            continue
        if not _valid_ohlc(c):
            limitations.append(f"{timeframe.value}: dropped invalid OHLC at {c.timestamp}")
            continue
        key = ensure_utc(c.timestamp)
        if not is_aligned_open(key, timeframe):
            misaligned += 1
            limitations.append(
                f"{timeframe.value}: dropped misaligned open at {key.isoformat()}"
            )
            continue
        # Prefer closed API rows; keep first occurrence for duplicates
        if key not in by_open:
            by_open[key] = c
        elif c.is_closed and not by_open[key].is_closed:
            by_open[key] = c

    ordered = sorted(by_open.values(), key=lambda x: ensure_utc(x.timestamp))
    step = timedelta(seconds=timeframe_to_seconds(timeframe))
    for i in range(1, len(ordered)):
        prev = ensure_utc(ordered[i - 1].timestamp)
        cur = ensure_utc(ordered[i].timestamp)
        expected = prev + step
        if cur > expected + timedelta(milliseconds=1):
            missing = int(round((cur - expected).total_seconds() / step.total_seconds()))
            gaps.append(
                CandleGapInfo(
                    timeframe=timeframe,
                    after_open=prev,
                    before_open=cur,
                    missing_estimate=max(1, missing),
                )
            )
    if gaps:
        limitations.append(f"{timeframe.value}: {len(gaps)} gap(s) detected.")
    if misaligned:
        limitations.append(
            f"{timeframe.value}: {misaligned} misaligned open timestamp(s) dropped."
        )
    return ordered, gaps, limitations
