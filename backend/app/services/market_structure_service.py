"""Fetch OHLCV and run the Market Structure Engine."""

from __future__ import annotations

from datetime import datetime, timezone

from app.analysis.market_structure import analyze_market_structure
from app.analysis.market_structure.config import DEFAULT_STRUCTURE_CONFIG, MarketStructureConfig
from app.api.schemas.market_structure import MarketStructureResponse
from app.exchanges.manager import get_exchange_manager
from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.market_data.normalizer import to_internal_symbol


async def compute_market_structure_response(
    *,
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    timeframe: Timeframe,
    limit: int = 500,
    include_unconfirmed: bool = False,
    config: MarketStructureConfig | None = None,
) -> MarketStructureResponse:
    internal = to_internal_symbol(symbol) if "/" not in symbol else symbol.upper()
    cfg = config or DEFAULT_STRUCTURE_CONFIG
    # Need enough history for swings + ATR warm-up
    fetch_limit = max(limit, 100)
    candles = await get_exchange_manager().fetch_ohlcv(
        exchange,
        internal,
        timeframe,
        market_type,
        limit=fetch_limit,
    )
    result = analyze_market_structure(
        candles,
        exchange=exchange,
        symbol=internal,
        market_type=market_type,
        timeframe=timeframe,
        config=cfg,
        include_unconfirmed=include_unconfirmed,
    )
    now = datetime.now(timezone.utc)
    return MarketStructureResponse(
        exchange=exchange,
        symbol=internal,
        market_type=market_type,
        timeframe=timeframe,
        calculated_at=now,
        data_source=f"{exchange.value}:{market_type.value}",
        include_unconfirmed=include_unconfirmed,
        config=result.config,
        snapshot=result.snapshot,
        swings=result.swings,
        unconfirmed_swings=result.unconfirmed_swings,
        bos_events=result.bos_events,
        choch_events=result.choch_events,
        mss_events=result.mss_events,
        ambiguous_dual_breaks=result.ambiguous_dual_breaks,
        metadata={
            "config_version": cfg.config_version,
            "closed_candles_used": result.snapshot.closed_candles_used,
            "event_count": {
                "swings": len(result.swings),
                "bos": len(result.bos_events),
                "choch": len(result.choch_events),
                "mss": len(result.mss_events),
                "ambiguous_dual_breaks": len(result.ambiguous_dual_breaks),
            },
            "active_level_semantics": {
                "active_unbroken_swing_high": "Latest unbroken confirmed Swing High (bullish break target)",
                "active_unbroken_swing_low": "Latest unbroken confirmed Swing Low (bearish break target)",
                "active_bullish_level": "Legacy alias of active_unbroken_swing_high",
                "active_bearish_level": "Legacy alias of active_unbroken_swing_low",
            },
            "strategy_phase": "3.2",
        },
    )
