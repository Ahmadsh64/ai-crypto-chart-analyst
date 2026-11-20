"""Fetch OHLCV via exchange manager and calculate indicators."""

from __future__ import annotations

from datetime import datetime, timezone

from app.analysis.indicators.calculator import calculate_indicators, round_latest_for_api
from app.analysis.indicators.models import (
    DEFAULT_INDICATORS,
    INDICATOR_PARAMS,
    WARMUP_REQUIREMENTS,
    IndicatorId,
)
from app.api.schemas.indicators import IndicatorsResponse
from app.exchanges.manager import get_exchange_manager
from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.market_data.normalizer import to_internal_symbol


def parse_indicator_ids(raw: str | None) -> list[IndicatorId]:
    if not raw:
        return list(DEFAULT_INDICATORS)
    items: list[IndicatorId] = []
    for part in raw.split(","):
        key = part.strip().lower()
        if not key:
            continue
        items.append(IndicatorId(key))
    return items or list(DEFAULT_INDICATORS)


async def compute_indicators_response(
    *,
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    timeframe: Timeframe,
    indicators: list[IndicatorId] | None = None,
    include_forming: bool = False,
    include_series: bool = False,
    limit: int = 500,
) -> IndicatorsResponse:
    internal = to_internal_symbol(symbol) if "/" not in symbol else symbol.upper()
    manager = get_exchange_manager()
    # Request enough history for EMA200 warm-up when possible.
    fetch_limit = max(limit, 250)
    candles = await manager.fetch_ohlcv(
        exchange,
        internal,
        timeframe,
        market_type,
        limit=fetch_limit,
    )
    selected = indicators or list(DEFAULT_INDICATORS)
    bundle = calculate_indicators(
        candles,
        indicators=selected,
        include_forming=include_forming,
        include_series=include_series,
    )
    latest = {key: round_latest_for_api(value) for key, value in bundle.latest.items()}
    series = bundle.series if include_series else {}
    now = datetime.now(timezone.utc)
    return IndicatorsResponse(
        exchange=exchange,
        symbol=internal,
        market_type=market_type,
        timeframe=timeframe,
        calculated_at=now,
        include_forming=include_forming,
        closed_candles_used=bundle.closed_candles_used,
        data_source=f"{exchange.value}:{market_type.value}",
        indicators=latest,
        series=series,
        available_indicators=[i.value for i in DEFAULT_INDICATORS],
        metadata={
            "warmup": {i.value: WARMUP_REQUIREMENTS[i] for i in selected},
            "params": {i.value: INDICATOR_PARAMS[i] for i in selected},
            "forming_included": bundle.forming_included,
            "default_closed_only": not include_forming,
            "include_series": include_series,
        },
    )
