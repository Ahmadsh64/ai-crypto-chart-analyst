"""Fetch OHLCV and run the Liquidity Engine."""

from __future__ import annotations

from datetime import datetime, timezone

from app.analysis.liquidity import analyze_liquidity
from app.analysis.liquidity.config import (
    DEFAULT_LIQUIDITY_CONFIG,
    LIQUIDITY_ANALYSIS_CANDLE_LIMIT,
    LiquidityConfig,
)
from app.api.schemas.liquidity import LiquidityResponse
from app.exchanges.manager import get_exchange_manager
from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.market_data.normalizer import to_internal_symbol


async def compute_liquidity_response(
    *,
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    timeframe: Timeframe,
    limit: int = LIQUIDITY_ANALYSIS_CANDLE_LIMIT,
    include_unconfirmed: bool = False,
    config: LiquidityConfig | None = None,
) -> LiquidityResponse:
    internal = to_internal_symbol(symbol) if "/" not in symbol else symbol.upper()
    cfg = config or DEFAULT_LIQUIDITY_CONFIG
    fetch_limit = max(limit, 100)
    candles = await get_exchange_manager().fetch_ohlcv(
        exchange,
        internal,
        timeframe,
        market_type,
        limit=fetch_limit,
    )
    result = analyze_liquidity(
        candles,
        exchange=exchange,
        symbol=internal,
        market_type=market_type,
        timeframe=timeframe,
        config=cfg,
        include_unconfirmed=include_unconfirmed,
    )
    now = datetime.now(timezone.utc)
    return LiquidityResponse(
        exchange=exchange,
        symbol=internal,
        market_type=market_type,
        timeframe=timeframe,
        calculated_at=now,
        data_source=f"{exchange.value}:{market_type.value}",
        include_unconfirmed=include_unconfirmed,
        config=result.config,
        snapshot=result.snapshot,
        eqh_clusters=result.eqh_clusters,
        eql_clusters=result.eql_clusters,
        bsl_levels=result.bsl_levels,
        ssl_levels=result.ssl_levels,
        sweeps=result.sweeps,
        provisional_sweeps=result.provisional_sweeps,
        ambiguous_crosses=result.ambiguous_crosses,
        metadata={
            "config_version": cfg.config_version,
            "closed_candles_used": result.snapshot.closed_candles_used,
            "candle_window": {
                "requested_limit": limit,
                "fetched": len(candles),
                "canonical_default": LIQUIDITY_ANALYSIS_CANDLE_LIMIT,
                "note": (
                    "snapshot.sweep_count equals len(sweeps) for this candle window; "
                    "sweeps are not independently paginated."
                ),
            },
            "event_count": {
                "eqh": len(result.eqh_clusters),
                "eql": len(result.eql_clusters),
                "bsl": len(result.bsl_levels),
                "ssl": len(result.ssl_levels),
                "sweeps": len(result.sweeps),
                "provisional_sweeps": len(result.provisional_sweeps),
                "ambiguous_crosses": len(result.ambiguous_crosses),
            },
            "strategy_phase": "3.3.1",
            "sweep_semantics": {
                "liquidity_type": "Authoritative pool swept (bsl|ssl)",
                "reaction_hint": (
                    "Contextual ICT reaction only — bearish after BSL sweep, "
                    "bullish after SSL sweep. Not a trade signal / not guaranteed."
                ),
                "direction": "DEPRECATED side label retained for backward compatibility",
            },
            "status_semantics": {
                "active": "Level detected; not yet swept or broken",
                "swept": "Wick beyond level + reclaim close",
                "broken": "Close beyond level (taken out, not a sweep)",
                "invalidated": "Reserved — not assigned in liq-v1.1.0-balanced",
            },
        },
    )
