"""Multi-Timeframe orchestration REST endpoints (Phase 4.1)."""

from fastapi import APIRouter, Query

from app.api.routes.market import _http_for_exchange_error, _normalize_symbol
from app.api.schemas.multi_timeframe import MultiTimeframeResponse
from app.exchanges.exceptions import ExchangeError
from app.exchanges.types import ExchangeId, MarketType
from app.services.multi_timeframe_service import compute_multi_timeframe_response

router = APIRouter(tags=["multi-timeframe"])


@router.get("/multi-timeframe", response_model=MultiTimeframeResponse)
async def get_multi_timeframe(
    exchange: ExchangeId = Query(...),
    market_type: MarketType = Query(...),
    symbol: str = Query(..., description="BTC/USDT or BTCUSDT"),
) -> MultiTimeframeResponse:
    """Synchronized 4H / 1H / 15M / 5M candle orchestration snapshot (no trade signals)."""
    internal = _normalize_symbol(symbol)
    try:
        return await compute_multi_timeframe_response(
            exchange=exchange,
            market_type=market_type,
            symbol=internal,
        )
    except ExchangeError as exc:
        raise _http_for_exchange_error(exc) from exc
