"""Multi-Timeframe candle orchestration — no trade decisions (Phase 4.1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.analysis.multi_timeframe.config import (
    DEFAULT_MTF_CONFIG,
    TIMEFRAME_DURATION_MINUTES,
    TIMEFRAME_PURPOSE,
    MultiTimeframeConfig,
)
from app.analysis.multi_timeframe.models import (
    CandleGap,
    MultiTimeframeSnapshot,
    OverallStatus,
    SyncMetadata,
    TimeframeSeriesSummary,
)
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.market_data.candles import timeframe_to_seconds
from app.market_data.normalizer import assert_homogeneous_series, is_valid_ohlc, sort_and_dedupe_candles


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def sanitize_candles(
    candles: list[Candle],
    *,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    as_of: datetime,
) -> list[Candle]:
    """Sort, dedupe, drop invalid / future candles. Preserve is_closed."""
    as_of = _ensure_utc(as_of)
    cleaned: list[Candle] = []
    for c in candles:
        if c.exchange != exchange or c.market_type != market_type:
            continue
        if c.symbol.upper() != symbol.upper():
            continue
        if not is_valid_ohlc(c.open, c.high, c.low, c.close, c.volume):
            continue
        ts = _ensure_utc(c.timestamp)
        if ts > as_of:
            continue
        if c.close_time is not None and _ensure_utc(c.close_time) > as_of and c.is_closed:
            # Closed flag claiming future close — treat as forming / drop from confirmed path later
            c = c.model_copy(update={"is_closed": False})
        cleaned.append(c if c.timestamp.tzinfo else c.model_copy(update={"timestamp": ts}))
    out = sort_and_dedupe_candles(cleaned)
    assert_homogeneous_series(out)
    return out


def split_closed_and_forming(
    candles: list[Candle],
    *,
    as_of: datetime,
) -> tuple[list[Candle], Candle | None]:
    """Confirmed series = closed only; at most one forming candle (latest open)."""
    as_of = _ensure_utc(as_of)
    closed: list[Candle] = []
    forming: Candle | None = None
    for c in candles:
        ts = _ensure_utc(c.timestamp)
        if ts > as_of:
            continue
        if c.is_closed:
            if c.close_time is not None and _ensure_utc(c.close_time) > as_of:
                continue
            closed.append(c)
        else:
            if forming is None or _ensure_utc(c.timestamp) >= _ensure_utc(forming.timestamp):
                forming = c
    return closed, forming


def detect_gaps(
    closed: list[Candle],
    timeframe: Timeframe,
    *,
    gap_factor: float,
) -> list[CandleGap]:
    step = timeframe_to_seconds(timeframe)
    if step <= 0 or len(closed) < 2:
        return []
    gaps: list[CandleGap] = []
    threshold = step * gap_factor
    for prev, curr in zip(closed, closed[1:]):
        delta = (_ensure_utc(curr.timestamp) - _ensure_utc(prev.timestamp)).total_seconds()
        if delta > threshold:
            missing = max(0, int(round(delta / step)) - 1)
            gaps.append(
                CandleGap(
                    after_timestamp=_ensure_utc(prev.timestamp),
                    before_timestamp=_ensure_utc(curr.timestamp),
                    expected_seconds=step,
                    actual_seconds=delta,
                    missing_estimate=missing,
                )
            )
    return gaps


def evaluate_timeframe_series(
    candles: list[Candle],
    *,
    timeframe: Timeframe,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    as_of: datetime | None = None,
    config: MultiTimeframeConfig | None = None,
    error: str | None = None,
) -> TimeframeSeriesSummary:
    cfg = config or DEFAULT_MTF_CONFIG
    hist = cfg.history_for(timeframe)
    now = _ensure_utc(as_of or datetime.now(timezone.utc))
    purpose = TIMEFRAME_PURPOSE[timeframe]
    duration = TIMEFRAME_DURATION_MINUTES[timeframe]

    if error:
        return TimeframeSeriesSummary(
            timeframe=timeframe,
            purpose=purpose,
            duration_minutes=duration,
            data_quality="error",
            status_detail=error,
            last_updated=now,
            is_ready=False,
        )

    sanitized = sanitize_candles(
        candles,
        exchange=exchange,
        symbol=symbol,
        market_type=market_type,
        as_of=now,
    )
    closed, forming = split_closed_and_forming(sanitized, as_of=now)
    gaps = detect_gaps(closed, timeframe, gap_factor=cfg.gap_factor)

    latest_any = sanitized[-1] if sanitized else None
    latest_closed = closed[-1] if closed else None
    latest_price = (
        (forming.close if forming is not None else None)
        or (latest_closed.close if latest_closed is not None else None)
    )

    is_stale = False
    if latest_closed is not None:
        max_age = timedelta(seconds=timeframe_to_seconds(timeframe) * cfg.stale_intervals)
        age_ref = latest_closed.close_time or (
            latest_closed.timestamp + timedelta(seconds=timeframe_to_seconds(timeframe))
        )
        is_stale = _ensure_utc(age_ref) + max_age < now

    has_gaps = len(gaps) > 0
    closed_count = len(closed)
    sufficient = closed_count >= hist.min_closed_candles

    if not sanitized:
        quality = "unavailable"
        detail = "No candles returned"
        ready = False
    elif not sufficient:
        quality = "insufficient"
        detail = f"Need ≥{hist.min_closed_candles} closed candles, have {closed_count}"
        ready = False
    elif is_stale:
        quality = "stale"
        detail = f"Latest closed candle older than {cfg.stale_intervals} intervals"
        ready = False
    elif has_gaps:
        quality = "gaps"
        detail = f"{len(gaps)} gap(s) detected in closed series"
        ready = True  # usable but flagged
    else:
        quality = "ok"
        detail = None
        ready = True

    preview_n = cfg.preview_closed_limit
    preview = closed[-preview_n:] if preview_n and closed else []

    return TimeframeSeriesSummary(
        timeframe=timeframe,
        purpose=purpose,
        duration_minutes=duration,
        latest_candle_time=_ensure_utc(latest_any.timestamp) if latest_any else None,
        latest_closed_candle_time=_ensure_utc(latest_closed.timestamp) if latest_closed else None,
        latest_price=latest_price,
        candles_count=len(sanitized),
        closed_candles_count=closed_count,
        is_ready=ready,
        is_stale=is_stale,
        has_data_gaps=has_gaps,
        data_quality=quality,
        status_detail=detail,
        last_updated=now,
        gap_count=len(gaps),
        gaps=gaps[:20],
        forming_candle=forming,
        recent_closed_candles=preview,
    )


def build_snapshot(
    series_by_tf: dict[Timeframe, TimeframeSeriesSummary],
    *,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    as_of: datetime | None = None,
    config: MultiTimeframeConfig | None = None,
) -> MultiTimeframeSnapshot:
    cfg = config or DEFAULT_MTF_CONFIG
    now = _ensure_utc(as_of or datetime.now(timezone.utc))
    ordered = [series_by_tf[tf] for tf in cfg.timeframes if tf in series_by_tf]
    # Include any unexpected keys last
    for tf, summary in series_by_tf.items():
        if tf not in cfg.timeframes:
            ordered.append(summary)

    ready = [s.timeframe for s in ordered if s.is_ready]
    unavailable = [s.timeframe for s in ordered if not s.is_ready]

    if len(ready) == len(ordered) and ordered:
        overall: OverallStatus = "ready"
    elif ready:
        overall = "partial"
    else:
        overall = "unavailable"

    sync = SyncMetadata(
        as_of=now,
        latest_closed_by_timeframe={
            s.timeframe.value: s.latest_closed_candle_time for s in ordered
        },
        forming_by_timeframe={
            s.timeframe.value: (
                _ensure_utc(s.forming_candle.timestamp) if s.forming_candle else None
            )
            for s in ordered
        },
        aligned=bool(ready) and all(
            s.latest_closed_candle_time is not None for s in ordered if s.is_ready
        ),
    )

    return MultiTimeframeSnapshot(
        exchange=exchange,
        symbol=symbol,
        market_type=market_type,
        calculated_at=now,
        config_version=cfg.config_version,
        overall_status=overall,
        ready_timeframes=ready,
        unavailable_timeframes=unavailable,
        timeframes=ordered,
        sync=sync,
        metadata={
            "strategy_phase": "4.1",
            "ladder": [tf.value for tf in cfg.timeframes],
            "no_trade_decisions": True,
        },
    )


def apply_candle_update(
    existing: list[Candle],
    candle: Candle,
    *,
    max_candles: int,
) -> list[Candle]:
    """Upsert a candle into a series (WS incremental)."""
    candles = list(existing)
    if candles and candles[-1].timestamp == candle.timestamp:
        candles[-1] = candle
    elif candles and candle.timestamp < candles[-1].timestamp:
        # Out of order — ignore for live path (no rewrite of history mid-stream)
        return candles
    else:
        candles.append(candle)
    if len(candles) > max_candles:
        candles = candles[-max_candles:]
    return candles
