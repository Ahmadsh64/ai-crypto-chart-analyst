"""Historical OHLCV loading via existing exchange adapters (Phase 5.1)."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.exchanges.manager import get_exchange_manager
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.market_data.candles import timeframe_to_seconds
from app.replay.config import DEFAULT_REPLAY_CONFIG, ReplayConfig
from app.replay.models import CandleGapInfo
from app.replay.timeline import ensure_utc, sanitize_series


async def load_replay_series(
    *,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    start: datetime,
    end: datetime,
    timeframes: tuple[Timeframe, ...] | None = None,
    config: ReplayConfig | None = None,
) -> tuple[dict[Timeframe, list[Candle]], list[CandleGapInfo], list[str]]:
    """
    Fetch each TF with start/end pagination (adapter-native).

    Does not fabricate gaps. Returns sanitized chronological series per TF.
    """
    cfg = config or DEFAULT_REPLAY_CONFIG
    tfs = timeframes or cfg.timeframes
    start = ensure_utc(start)
    end = ensure_utc(end)
    if end <= start:
        raise ValueError("end_time must be after start_time")

    manager = get_exchange_manager()
    series: dict[Timeframe, list[Candle]] = {}
    all_gaps: list[CandleGapInfo] = []
    limitations: list[str] = []

    for tf in tfs:
        # Estimate candle count needed for coverage (+ small buffer)
        span_sec = (end - start).total_seconds()
        tf_sec = timeframe_to_seconds(tf)
        estimate = int(span_sec / tf_sec) + 5
        limit = min(cfg.max_candles_per_timeframe, max(50, estimate))
        try:
            raw = await manager.fetch_ohlcv(
                exchange,
                symbol,
                tf,
                market_type,
                limit=limit,
                start=start,
                end=end,
            )
        except Exception as exc:  # noqa: BLE001
            limitations.append(f"{tf.value}: fetch failed — {exc}")
            series[tf] = []
            continue

        # Allow one parent bar that opened just before start.
        filtered = [
            c
            for c in raw
            if ensure_utc(c.timestamp) >= start - timedelta(seconds=tf_sec)
            and ensure_utc(c.timestamp) <= end
        ]
        cleaned, gaps, notes = sanitize_series(
            filtered,
            exchange=exchange,
            symbol=symbol,
            market_type=market_type,
            timeframe=tf,
        )
        series[tf] = cleaned
        all_gaps.extend(gaps)
        limitations.extend(notes)
        if not cleaned:
            limitations.append(f"{tf.value}: no candles in requested range.")

    return series, all_gaps, limitations
