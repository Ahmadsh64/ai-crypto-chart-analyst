"""Build historical candle prefixes for analysis (Phase 5.2.1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.replay.analysis.config import (
    DEFAULT_HISTORICAL_ANALYSIS_CONFIG,
    HistoricalAnalysisConfig,
)
from app.replay.analysis.validation import filter_closed_prefix
from app.replay.timeline import ensure_utc


@dataclass(frozen=True)
class HistoricalPrefixContext:
    session_id: str
    replay_timestamp: datetime
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    candles_by_tf: dict[Timeframe, list[Candle]]
    closed_counts: dict[Timeframe, int]
    limitations: list[str]
    is_ready: bool


def build_historical_prefixes(
    *,
    session_id: str,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    series_by_tf: dict[Timeframe, list[Candle]],
    clock: datetime,
    config: HistoricalAnalysisConfig | None = None,
) -> HistoricalPrefixContext:
    """
    Explicitly construct closed-candle prefixes at ``clock``.

    Never passes the full historical series to engines — only confirmed bars.
    """
    cfg = config or DEFAULT_HISTORICAL_ANALYSIS_CONFIG
    clock = ensure_utc(clock)
    candles_by_tf: dict[Timeframe, list[Candle]] = {}
    closed_counts: dict[Timeframe, int] = {}
    limitations: list[str] = []

    for tf in cfg.timeframes:
        series = series_by_tf.get(tf, [])
        prefix = filter_closed_prefix(series, timeframe=tf, clock=clock)
        # Engines treat is_closed as confirmation gate — force True for closed prefix.
        normalized: list[Candle] = []
        for c in prefix:
            if c.is_closed:
                normalized.append(c)
            else:
                normalized.append(c.model_copy(update={"is_closed": True}))
        candles_by_tf[tf] = normalized
        closed_counts[tf] = len(normalized)
        if not normalized:
            limitations.append(f"{tf.value}: no confirmed candles at replay clock.")
        elif len(normalized) < 20:
            limitations.append(
                f"{tf.value}: only {len(normalized)} confirmed candles (warming up)."
            )

    ready = all(closed_counts.get(tf, 0) >= 1 for tf in cfg.timeframes)
    return HistoricalPrefixContext(
        session_id=session_id,
        replay_timestamp=clock,
        exchange=exchange,
        symbol=symbol.upper(),
        market_type=market_type,
        candles_by_tf=candles_by_tf,
        closed_counts=closed_counts,
        limitations=limitations,
        is_ready=ready,
    )
