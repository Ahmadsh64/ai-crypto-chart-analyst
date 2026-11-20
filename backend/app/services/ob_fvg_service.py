"""Fetch OHLCV and run the OB/FVG engine."""

from __future__ import annotations

from datetime import datetime, timezone

from app.analysis.ob_fvg import analyze_ob_fvg
from app.analysis.ob_fvg.config import (
    DEFAULT_OB_FVG_CONFIG,
    OB_FVG_ANALYSIS_CANDLE_LIMIT,
    ObFvgConfig,
)
from app.api.schemas.ob_fvg import ObFvgResponse
from app.exchanges.manager import get_exchange_manager
from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.market_data.normalizer import to_internal_symbol


async def compute_ob_fvg_response(
    *,
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    timeframe: Timeframe,
    limit: int = OB_FVG_ANALYSIS_CANDLE_LIMIT,
    include_unconfirmed: bool = False,
    config: ObFvgConfig | None = None,
) -> ObFvgResponse:
    internal = to_internal_symbol(symbol) if "/" not in symbol else symbol.upper()
    cfg = config or DEFAULT_OB_FVG_CONFIG
    fetch_limit = max(limit, 100)
    candles = await get_exchange_manager().fetch_ohlcv(
        exchange,
        internal,
        timeframe,
        market_type,
        limit=fetch_limit,
    )
    result = analyze_ob_fvg(
        candles,
        exchange=exchange,
        symbol=internal,
        market_type=market_type,
        timeframe=timeframe,
        config=cfg,
        include_unconfirmed=include_unconfirmed,
    )
    now = datetime.now(timezone.utc)
    return ObFvgResponse(
        exchange=exchange,
        symbol=internal,
        market_type=market_type,
        timeframe=timeframe,
        calculated_at=now,
        data_source=f"{exchange.value}:{market_type.value}",
        include_unconfirmed=include_unconfirmed,
        config=result.config,
        snapshot=result.snapshot,
        bullish_order_blocks=result.bullish_order_blocks,
        bearish_order_blocks=result.bearish_order_blocks,
        bullish_fvgs=result.bullish_fvgs,
        bearish_fvgs=result.bearish_fvgs,
        provisional_order_blocks=result.provisional_order_blocks,
        provisional_fvgs=result.provisional_fvgs,
        metadata={
            "config_version": cfg.config_version,
            "closed_candles_used": result.snapshot.closed_candles_used,
            "candle_window": {
                "requested_limit": limit,
                "fetched": len(candles),
                "canonical_default": OB_FVG_ANALYSIS_CANDLE_LIMIT,
            },
            "strategy_phase": "3.4",
            "ob_status_semantics": {
                "active": "Detected; not yet touched",
                "partially_mitigated": "Price overlapped the zone",
                "mitigated": "Price fully traversed the zone (precedence over invalidation)",
                "invalidated": "Close beyond far boundary before full mitigation",
            },
            "fvg_status_semantics": {
                "active": "Gap open",
                "partially_filled": "Price overlapped the gap",
                "filled": "Price fully traversed the gap",
                "invalidated": "Close beyond far boundary before fill",
            },
        },
    )
