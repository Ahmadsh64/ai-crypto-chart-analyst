"""Market data REST endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app.api.schemas.market import (
    CandlesResponse,
    ExchangesResponse,
    MarketsResponse,
    TickerResponse,
)
from app.exchanges.exceptions import (
    ExchangeError,
    ExchangeRateLimitError,
    ExchangeRequestError,
    ExchangeUnsupportedError,
)
from app.exchanges.manager import get_exchange_manager
from app.exchanges.types import DEFAULT_SYMBOLS, ExchangeId, MarketType, Timeframe
from app.market_data.normalizer import to_internal_symbol

router = APIRouter(tags=["market"])


def _http_for_exchange_error(exc: ExchangeError) -> HTTPException:
    if isinstance(exc, ExchangeUnsupportedError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, ExchangeRateLimitError):
        return HTTPException(status_code=429, detail=str(exc))
    if isinstance(exc, ExchangeRequestError):
        if exc.status_code == 404:
            return HTTPException(status_code=404, detail=str(exc))
        status = 502 if (exc.status_code or 500) >= 500 else 400
        return HTTPException(status_code=status, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


def _normalize_symbol(symbol: str) -> str:
    cleaned = symbol.strip().upper().replace("-", "/")
    if "/" not in cleaned:
        return to_internal_symbol(cleaned)
    return cleaned


@router.get("/exchanges", response_model=ExchangesResponse)
async def list_exchanges() -> ExchangesResponse:
    manager = get_exchange_manager()
    exchanges = manager.list_exchanges()
    pings = await manager.ping_all()
    annotated = []
    for info in exchanges:
        status = "ok" if pings.get(info.id) else "unavailable"
        annotated.append(info.model_copy(update={"status": status}))
    return ExchangesResponse(
        exchanges=annotated,
        default_symbols=list(DEFAULT_SYMBOLS),
        timeframes=list(Timeframe),
    )


@router.get("/markets", response_model=MarketsResponse)
async def list_markets(
    exchange: ExchangeId = Query(...),
    market_type: MarketType = Query(...),
    search: str | None = Query(
        default=None,
        description="Filter by symbol, native symbol, base, or quote (e.g. BTC, USDT, BTCUSDT)",
    ),
    limit: int | None = Query(
        default=None,
        ge=1,
        le=5000,
        description="Optional page size. Omit to return the full filtered list.",
    ),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    refresh: bool = Query(
        default=False,
        description="Bypass metadata cache and refetch from the exchange",
    ),
) -> MarketsResponse:
    from app.market_data.markets_cache import (
        filter_trading_pairs,
        get_markets_cache,
        paginate_pairs,
    )

    manager = get_exchange_manager()
    cache = get_markets_cache()
    cache_hit = False
    try:
        if refresh:
            cache.invalidate(exchange, market_type)

        cached = None if refresh else cache.get(exchange, market_type)
        if cached is not None:
            pairs = cached
            cache_hit = True
        else:
            pairs = await manager.list_markets(exchange, market_type)
            # Only cache active instruments.
            pairs = [p for p in pairs if getattr(p, "active", True)]
            cache.set(exchange, market_type, pairs)
    except ExchangeError as exc:
        raise _http_for_exchange_error(exc) from exc

    filtered = filter_trading_pairs(pairs, search)
    page, total = paginate_pairs(filtered, limit=limit, offset=offset)

    now = datetime.now(timezone.utc)
    return MarketsResponse(
        exchange=exchange,
        market_type=market_type,
        count=len(page),
        pairs=page,
        last_updated=now,
        data_source=f"{exchange.value}:{market_type.value}",
        total=total,
        limit=limit,
        offset=offset,
        cache_hit=cache_hit,
    )


@router.get("/market/candles", response_model=CandlesResponse)
async def get_candles(
    exchange: ExchangeId = Query(...),
    market_type: MarketType = Query(...),
    symbol: str = Query(..., description="Internal symbol e.g. BTC/USDT or native BTCUSDT"),
    timeframe: Timeframe = Query(default=Timeframe.H1),
    limit: int = Query(default=300, ge=1, le=5000),
) -> CandlesResponse:
    manager = get_exchange_manager()
    internal = _normalize_symbol(symbol)
    try:
        candles = await manager.fetch_ohlcv(
            exchange,
            internal,
            timeframe,
            market_type,
            limit=limit,
        )
    except ExchangeError as exc:
        raise _http_for_exchange_error(exc) from exc

    if not candles:
        raise HTTPException(status_code=404, detail="No candle data returned")

    now = datetime.now(timezone.utc)
    latest = candles[-1].close
    return CandlesResponse(
        exchange=exchange,
        market_type=market_type,
        symbol=internal,
        timeframe=timeframe,
        count=len(candles),
        candles=candles,
        latest_price=latest,
        last_updated=now,
        updated_at=now,
        data_source=f"{exchange.value}:{market_type.value}",
    )


@router.get("/market/ticker", response_model=TickerResponse)
async def get_ticker(
    exchange: ExchangeId = Query(...),
    market_type: MarketType = Query(...),
    symbol: str = Query(..., description="Internal symbol e.g. BTC/USDT or native BTCUSDT"),
) -> TickerResponse:
    manager = get_exchange_manager()
    internal = _normalize_symbol(symbol)
    try:
        ticker = await manager.fetch_ticker(exchange, internal, market_type)
    except ExchangeError as exc:
        raise _http_for_exchange_error(exc) from exc
    now = datetime.now(timezone.utc)
    return TickerResponse(
        ticker=ticker,
        last_updated=now,
        data_source=f"{exchange.value}:{market_type.value}",
    )
