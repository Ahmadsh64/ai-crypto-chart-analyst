"""Bybit public market-data adapter (Spot + Linear Perpetual)."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.core.config import get_settings
from app.exchanges.base import BaseExchange
from app.exchanges.exceptions import (
    ExchangeRateLimitError,
    ExchangeRequestError,
    ExchangeUnsupportedError,
)
from app.exchanges.http import DEFAULT_TIMEOUT, with_retries
from app.exchanges.types import (
    Candle,
    ExchangeId,
    MarketType,
    Ticker,
    Timeframe,
    TradingPair,
)
from app.market_data.candles import MAX_PAGE_SIZE, clamp_page_size, previous_page_end
from app.market_data.normalizer import (
    assert_homogeneous_series,
    normalize_bybit_kline,
    sort_and_dedupe_candles,
    to_internal_symbol,
    to_native_symbol,
)

BYBIT_INTERVALS: dict[Timeframe, str] = {
    Timeframe.M1: "1",
    Timeframe.M5: "5",
    Timeframe.M15: "15",
    Timeframe.M30: "30",
    Timeframe.H1: "60",
    Timeframe.H4: "240",
    Timeframe.D1: "D",
}

BYBIT_CATEGORY: dict[MarketType, str] = {
    MarketType.SPOT: "spot",
    MarketType.LINEAR_PERPETUAL: "linear",
}


class BybitExchange(BaseExchange):
    exchange_id = ExchangeId.BYBIT
    supported_market_types = (MarketType.SPOT, MarketType.LINEAR_PERPETUAL)

    def __init__(self, client: httpx.AsyncClient) -> None:
        super().__init__(client)
        settings = get_settings()
        self._base = settings.bybit_base_url.rstrip("/")

    def _category(self, market_type: MarketType) -> str:
        self.ensure_market_type(market_type)
        return BYBIT_CATEGORY[market_type]

    async def _get(self, path: str, params: dict) -> dict:
        url = f"{self._base}{path}"

        async def _once() -> dict:
            response = await self._client.get(url, params=params, timeout=DEFAULT_TIMEOUT)
            if response.status_code == 429:
                raise ExchangeRateLimitError(
                    "Bybit rate limit exceeded",
                    exchange=self.exchange_id.value,
                    status_code=429,
                )
            if response.status_code >= 400:
                raise ExchangeRequestError(
                    f"Bybit HTTP {response.status_code}: {response.text[:300]}",
                    exchange=self.exchange_id.value,
                    status_code=response.status_code,
                )
            payload = response.json()
            ret_code = payload.get("retCode")
            if ret_code not in (0, "0", None):
                raise ExchangeRequestError(
                    f"Bybit error {ret_code}: {payload.get('retMsg')}",
                    exchange=self.exchange_id.value,
                    status_code=response.status_code,
                )
            return payload

        return await with_retries(_once, exchange=self.exchange_id.value)

    async def ping(self) -> bool:
        try:
            payload = await self._get("/v5/market/time", {})
            return "result" in payload or payload.get("retCode") in (0, "0")
        except ExchangeRequestError:
            return False

    async def list_markets(self, market_type: MarketType) -> list[TradingPair]:
        category = self._category(market_type)
        payload = await self._get(
            "/v5/market/instruments-info",
            {"category": category, "limit": 1000},
        )
        result = payload.get("result") or {}
        items = result.get("list") or []
        pairs: list[TradingPair] = []
        for item in items:
            status = (item.get("status") or "").upper()
            if status and status not in {"TRADING", "ACTIVE"}:
                continue
            quote = item.get("quoteCoin") or ""
            base = item.get("baseCoin") or ""
            if quote != "USDT":
                continue
            if market_type == MarketType.LINEAR_PERPETUAL:
                contract_type = (item.get("contractType") or "").lower()
                if contract_type and "perpetual" not in contract_type:
                    continue
            native = item.get("symbol") or ""
            pairs.append(
                TradingPair(
                    symbol=f"{base}/{quote}" if base and quote else to_internal_symbol(native),
                    base=base,
                    quote=quote,
                    exchange=self.exchange_id,
                    market_type=market_type,
                    native_symbol=native,
                    active=True,
                )
            )
        return sorted(pairs, key=lambda p: p.symbol)

    async def _fetch_ohlcv_page(
        self,
        *,
        symbol: str,
        timeframe: Timeframe,
        market_type: MarketType,
        limit: int,
        start: datetime | None,
        end: datetime | None,
    ) -> list[Candle]:
        native = to_native_symbol(symbol)
        internal = to_internal_symbol(symbol) if "/" in symbol else to_internal_symbol(native)
        params: dict[str, str | int] = {
            "category": self._category(market_type),
            "symbol": native,
            "interval": BYBIT_INTERVALS[timeframe],
            "limit": clamp_page_size(limit),
        }
        if start is not None:
            params["start"] = int(start.timestamp() * 1000)
        if end is not None:
            params["end"] = int(end.timestamp() * 1000)

        payload = await self._get("/v5/market/kline", params)
        rows = (payload.get("result") or {}).get("list") or []
        now = datetime.now(timezone.utc)
        candles: list[Candle] = []
        # Bybit returns newest-first; reverse to ascending for this page.
        for row in reversed(rows):
            candle = normalize_bybit_kline(
                row,
                exchange=self.exchange_id,
                symbol=internal,
                market_type=market_type,
                timeframe=timeframe,
                now=now,
            )
            if candle is not None:
                candles.append(candle)
        return candles

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        market_type: MarketType,
        *,
        limit: int = 500,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Candle]:
        if timeframe not in BYBIT_INTERVALS:
            raise ExchangeUnsupportedError(
                f"Unsupported timeframe: {timeframe}",
                exchange=self.exchange_id.value,
            )

        target = max(1, limit)
        collected: list[Candle] = []
        cursor_end = end

        while len(collected) < target:
            page_limit = min(MAX_PAGE_SIZE, target - len(collected))
            page = await self._fetch_ohlcv_page(
                symbol=symbol,
                timeframe=timeframe,
                market_type=market_type,
                limit=page_limit,
                start=start,
                end=cursor_end,
            )
            if not page:
                break
            collected = page + collected
            if len(page) < page_limit:
                break
            cursor_end = previous_page_end(page[0])
            if start is not None and cursor_end <= start:
                break

        candles = sort_and_dedupe_candles(collected)[-target:]
        assert_homogeneous_series(candles)
        return candles

    async def fetch_ticker(self, symbol: str, market_type: MarketType) -> Ticker:
        native = to_native_symbol(symbol)
        payload = await self._get(
            "/v5/market/tickers",
            {"category": self._category(market_type), "symbol": native},
        )
        items = (payload.get("result") or {}).get("list") or []
        if not items:
            raise ExchangeRequestError(
                f"No Bybit ticker for {native}",
                exchange=self.exchange_id.value,
                status_code=404,
            )
        data = items[0]
        change = data.get("price24hPcnt")
        change_pct = float(change) * 100 if change not in (None, "") else None
        return Ticker(
            symbol=to_internal_symbol(native),
            exchange=self.exchange_id,
            market_type=market_type,
            last=float(data["lastPrice"]),
            bid=float(data["bid1Price"]) if data.get("bid1Price") not in (None, "") else None,
            ask=float(data["ask1Price"]) if data.get("ask1Price") not in (None, "") else None,
            high_24h=float(data["highPrice24h"]) if data.get("highPrice24h") else None,
            low_24h=float(data["lowPrice24h"]) if data.get("lowPrice24h") else None,
            volume_24h=float(data["volume24h"]) if data.get("volume24h") else None,
            change_pct_24h=change_pct,
            updated_at=datetime.now(timezone.utc),
        )
