"""Market Structure REST endpoints."""

from fastapi import APIRouter, Query

from app.api.routes.market import _http_for_exchange_error, _normalize_symbol
from app.api.schemas.market_structure import MarketStructureResponse
from app.exchanges.exceptions import ExchangeError
from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.services.market_structure_service import compute_market_structure_response

router = APIRouter(tags=["market-structure"])


@router.get("/market-structure", response_model=MarketStructureResponse)
async def get_market_structure(
    exchange: ExchangeId = Query(...),
    market_type: MarketType = Query(...),
    symbol: str = Query(..., description="BTC/USDT or BTCUSDT"),
    timeframe: Timeframe = Query(default=Timeframe.H1),
    limit: int = Query(default=500, ge=50, le=2000),
    include_unconfirmed: bool = Query(
        default=False,
        description="If true, include candidate pivots lacking right-side confirmation.",
    ),
) -> MarketStructureResponse:
    internal = _normalize_symbol(symbol)
    try:
        return await compute_market_structure_response(
            exchange=exchange,
            market_type=market_type,
            symbol=internal,
            timeframe=timeframe,
            limit=limit,
            include_unconfirmed=include_unconfirmed,
        )
    except ExchangeError as exc:
        raise _http_for_exchange_error(exc) from exc
