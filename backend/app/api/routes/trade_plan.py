"""Trade-plan REST endpoint (Phase 4.3)."""

from fastapi import APIRouter, Query

from app.api.routes.market import _http_for_exchange_error, _normalize_symbol
from app.api.schemas.trade_plan import TradePlanResponse
from app.exchanges.exceptions import ExchangeError
from app.exchanges.types import ExchangeId, MarketType
from app.services.trade_plan_service import compute_trade_plan_response

router = APIRouter(tags=["trade-plan"])


@router.get("/trade-plan", response_model=TradePlanResponse)
async def get_trade_plan(
    exchange: ExchangeId = Query(...),
    market_type: MarketType = Query(...),
    symbol: str = Query(..., description="BTC/USDT or BTCUSDT"),
    account_balance: float | None = Query(
        default=None,
        description="Hypothetical account balance (not a real exchange balance).",
        gt=0,
    ),
    risk_percent: float | None = Query(
        default=None,
        description="Hypothetical risk percent of account balance (default 1).",
        gt=0,
        le=5,
    ),
) -> TradePlanResponse:
    """Deterministic hypothetical trade plan from strong confluence (analysis only)."""
    internal = _normalize_symbol(symbol)
    try:
        return await compute_trade_plan_response(
            exchange=exchange,
            market_type=market_type,
            symbol=internal,
            account_balance=account_balance,
            risk_percent=risk_percent,
        )
    except ExchangeError as exc:
        raise _http_for_exchange_error(exc) from exc
