"""Technical indicators REST endpoints."""

from fastapi import APIRouter, HTTPException, Query

from app.analysis.indicators.models import (
    DEFAULT_INDICATORS,
    INDICATOR_PARAMS,
    WARMUP_REQUIREMENTS,
)
from app.api.schemas.indicators import IndicatorMetaItem, IndicatorsCatalogResponse, IndicatorsResponse
from app.exchanges.exceptions import ExchangeError
from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.api.routes.market import _http_for_exchange_error, _normalize_symbol
from app.services.indicator_service import compute_indicators_response, parse_indicator_ids

router = APIRouter(tags=["indicators"])


@router.get("/indicators/catalog", response_model=IndicatorsCatalogResponse)
async def indicators_catalog() -> IndicatorsCatalogResponse:
    return IndicatorsCatalogResponse(
        indicators=[
            IndicatorMetaItem(
                id=ind.value,
                params=dict(INDICATOR_PARAMS[ind]),
                warmup_required=WARMUP_REQUIREMENTS[ind],
            )
            for ind in DEFAULT_INDICATORS
        ]
    )


@router.get("/indicators", response_model=IndicatorsResponse)
async def get_indicators(
    exchange: ExchangeId = Query(...),
    market_type: MarketType = Query(...),
    symbol: str = Query(..., description="BTC/USDT or BTCUSDT"),
    timeframe: Timeframe = Query(default=Timeframe.H1),
    indicators: str | None = Query(
        default=None,
        description="Comma-separated indicator ids, e.g. ema_20,rsi_14,macd",
    ),
    include_forming: bool = Query(
        default=False,
        description="If true, include the currently forming candle (live/unstable).",
    ),
    include_series: bool = Query(
        default=False,
        description="If true, include full timestamp-aligned series (for chart overlays).",
    ),
    limit: int = Query(default=500, ge=50, le=2000),
) -> IndicatorsResponse:
    internal = _normalize_symbol(symbol)
    try:
        selected = parse_indicator_ids(indicators)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown indicator id: {exc}") from exc

    try:
        return await compute_indicators_response(
            exchange=exchange,
            market_type=market_type,
            symbol=internal,
            timeframe=timeframe,
            indicators=selected,
            include_forming=include_forming,
            include_series=include_series,
            limit=limit,
        )
    except ExchangeError as exc:
        raise _http_for_exchange_error(exc) from exc
