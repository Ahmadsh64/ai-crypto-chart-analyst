"""Confluence REST endpoint (Phase 4.2)."""

from fastapi import APIRouter, Query

from app.api.routes.market import _http_for_exchange_error, _normalize_symbol
from app.api.schemas.confluence import ConfluenceResponse
from app.exchanges.exceptions import ExchangeError
from app.exchanges.types import ExchangeId, MarketType
from app.services.confluence_service import compute_confluence_response

router = APIRouter(tags=["confluence"])


@router.get("/confluence", response_model=ConfluenceResponse)
async def get_confluence(
    exchange: ExchangeId = Query(...),
    market_type: MarketType = Query(...),
    symbol: str = Query(..., description="BTC/USDT or BTCUSDT"),
) -> ConfluenceResponse:
    """Deterministic multi-timeframe confluence scores (preliminary assessment only)."""
    internal = _normalize_symbol(symbol)
    try:
        return await compute_confluence_response(
            exchange=exchange,
            market_type=market_type,
            symbol=internal,
        )
    except ExchangeError as exc:
        raise _http_for_exchange_error(exc) from exc
