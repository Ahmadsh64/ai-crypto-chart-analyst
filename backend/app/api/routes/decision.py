"""Final decision REST endpoint (Phase 4.4)."""

from fastapi import APIRouter, Query

from app.api.routes.market import _http_for_exchange_error, _normalize_symbol
from app.api.schemas.decision import DecisionResponse
from app.exchanges.exceptions import ExchangeError
from app.exchanges.types import ExchangeId, MarketType
from app.services.decision_service import compute_decision_response

router = APIRouter(tags=["decision"])


@router.get("/decision", response_model=DecisionResponse)
async def get_decision(
    exchange: ExchangeId = Query(...),
    market_type: MarketType = Query(...),
    symbol: str = Query(..., description="BTC/USDT or BTCUSDT"),
    account_balance: float | None = Query(default=None, gt=0),
    risk_percent: float | None = Query(default=None, gt=0, le=5),
) -> DecisionResponse:
    """Deterministic final analytical decision (LONG/SHORT/WAIT/NO TRADE)."""
    internal = _normalize_symbol(symbol)
    try:
        return await compute_decision_response(
            exchange=exchange,
            market_type=market_type,
            symbol=internal,
            account_balance=account_balance,
            risk_percent=risk_percent,
        )
    except ExchangeError as exc:
        raise _http_for_exchange_error(exc) from exc
