"""Order Block / FVG REST endpoints (Phase 3.4)."""

from fastapi import APIRouter, Query

from app.analysis.ob_fvg.config import OB_FVG_ANALYSIS_CANDLE_LIMIT
from app.api.routes.market import _http_for_exchange_error, _normalize_symbol
from app.api.schemas.ob_fvg import ObFvgResponse
from app.exchanges.exceptions import ExchangeError
from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.services.ob_fvg_service import compute_ob_fvg_response

router = APIRouter(tags=["ob-fvg"])


@router.get("/ob-fvg", response_model=ObFvgResponse)
async def get_ob_fvg(
    exchange: ExchangeId = Query(...),
    market_type: MarketType = Query(...),
    symbol: str = Query(..., description="BTC/USDT or BTCUSDT"),
    timeframe: Timeframe = Query(default=Timeframe.H1),
    limit: int = Query(
        default=OB_FVG_ANALYSIS_CANDLE_LIMIT,
        ge=50,
        le=2000,
        description="Candle window (canonical default matches WebSocket max_candles).",
    ),
    include_unconfirmed: bool = Query(
        default=False,
        description="If true, include provisional FVGs from the forming candle.",
    ),
) -> ObFvgResponse:
    internal = _normalize_symbol(symbol)
    try:
        return await compute_ob_fvg_response(
            exchange=exchange,
            market_type=market_type,
            symbol=internal,
            timeframe=timeframe,
            limit=limit,
            include_unconfirmed=include_unconfirmed,
        )
    except ExchangeError as exc:
        raise _http_for_exchange_error(exc) from exc
