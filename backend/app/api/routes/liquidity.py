"""Liquidity REST endpoints (Phase 3.3)."""

from fastapi import APIRouter, Query

from app.api.routes.market import _http_for_exchange_error, _normalize_symbol
from app.api.schemas.liquidity import LiquidityResponse
from app.exchanges.exceptions import ExchangeError
from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.analysis.liquidity.config import LIQUIDITY_ANALYSIS_CANDLE_LIMIT
from app.services.liquidity_service import compute_liquidity_response

router = APIRouter(tags=["liquidity"])


@router.get("/liquidity", response_model=LiquidityResponse)
async def get_liquidity(
    exchange: ExchangeId = Query(...),
    market_type: MarketType = Query(...),
    symbol: str = Query(..., description="BTC/USDT or BTCUSDT"),
    timeframe: Timeframe = Query(default=Timeframe.H1),
    limit: int = Query(
        default=LIQUIDITY_ANALYSIS_CANDLE_LIMIT,
        ge=50,
        le=2000,
        description=(
            "Candle window size (same canonical default as WebSocket "
            f"max_candles={LIQUIDITY_ANALYSIS_CANDLE_LIMIT}). "
            "sweep_count == len(sweeps) for this window; sweeps are not paginated."
        ),
    ),
    include_unconfirmed: bool = Query(
        default=False,
        description="If true, include provisional sweeps from the forming candle.",
    ),
) -> LiquidityResponse:
    internal = _normalize_symbol(symbol)
    try:
        return await compute_liquidity_response(
            exchange=exchange,
            market_type=market_type,
            symbol=internal,
            timeframe=timeframe,
            limit=limit,
            include_unconfirmed=include_unconfirmed,
        )
    except ExchangeError as exc:
        raise _http_for_exchange_error(exc) from exc
