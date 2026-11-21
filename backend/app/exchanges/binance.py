"""Binance public market-data adapter (Spot + USDT-M Futures)."""

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
    normalize_binance_kline,
    sort_and_dedupe_candles,
    to_internal_symbol,
    to_native_symbol,
)

BINANCE_INTERVALS: dict[Timeframe, str] = {
    Timeframe.M1: "1m",
    Timeframe.M5: "5m",
    Timeframe.M15: "15m",
    Timeframe.M30: "30m",
    Timeframe.H1: "1h",
    Timeframe.H4: "4h",
    Timeframe.D1: "1d",
}


class BinanceExchange(BaseExchange):
    exchange_id = ExchangeId.BINANCE
    supported_market_types = (MarketType.SPOT, MarketType.USDT_M_FUTURES)

    def __init__(self, client: httpx.AsyncClient) -> None:
        super().__init__(client)
        settings = get_settings()
        self._spot_base = settings.binance_base_url.rstrip("/")
        self._futures_base = settings.binance_futures_base_url.rstrip("/")

    def _base_for(self, market_type: MarketType) -> str:
        self.ensure_market_type(market_type)
        if market_type == MarketType.SPOT:
            return self._spot_base
        return self._futures_base

    async def _get(self, base: str, path: str, params: dict) -> httpx.Response:
        url = f"{base}{path}"

        async def _once() -> httpx.Response:
            response = await self._client.get(url, params=params, timeout=DEFAULT_TIMEOUT)
            if response.status_code == 429:
                raise ExchangeRateLimitError(
                    "Binance rate limit exceeded",
                    exchange=self.exchange_id.value,
                    status_code=429,
                )
            if response.status_code >= 400:
                raise ExchangeRequestError(
                    f"Binance HTTP {response.status_code}: {response.text[:300]}",
                    exchange=self.exchange_id.value,
                    status_code=response.status_code,
                )
            return response

        return await with_retries(_once, exchange=self.exchange_id.value)

    async def ping(self) -> bool:
        try:
            response = await self._get(self._spot_base, "/api/v3/ping", {})
            return response.status_code == 200
        except ExchangeRequestError:
            return False

    async def list_markets(self, market_type: MarketType) -> list[TradingPair]:
        base = self._base_for(market_type)
        if market_type == MarketType.SPOT:
            response = await self._get(base, "/api/v3/exchangeInfo", {})
            payload = response.json()
            pairs: list[TradingPair] = []
            for item in payload.get("symbols", []):
                if item.get("status") != "TRADING":
                    continue
                if item.get("quoteAsset") != "USDT":
                    continue
                pairs.append(
                    TradingPair(
                        symbol=f"{item['baseAsset']}/{item['quoteAsset']}",
                        base=item["baseAsset"],
                        quote=item["quoteAsset"],
                        exchange=self.exchange_id,
                        market_type=market_type,
                        native_symbol=item["symbol"],
                        active=True,
                    )
                )
            return sorted(pairs, key=lambda p: p.symbol)

        response = await self._get(base, "/fapi/v1/exchangeInfo", {})
        payload = response.json()
        pairs = []
        for item in payload.get("symbols", []):
            if item.get("status") != "TRADING":
                continue
            if item.get("quoteAsset") != "USDT":
                continue
            if item.get("contractType") and item.get("contractType") != "PERPETUAL":
                continue
            pairs.append(
                TradingPair(
                    symbol=f"{item['baseAsset']}/{item['quoteAsset']}",
                    base=item["baseAsset"],
                    quote=item["quoteAsset"],
                    exchange=self.exchange_id,
                    market_type=market_type,
                    native_symbol=item["symbol"],
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
        base = self._base_for(market_type)
        native = to_native_symbol(symbol)
        internal = to_internal_symbol(symbol) if "/" in symbol else to_internal_symbol(native)
        params: dict[str, str | int] = {
            "symbol": native,
            "interval": BINANCE_INTERVALS[timeframe],
            "limit": clamp_page_size(limit),
        }
        if start is not None:
            params["startTime"] = int(start.timestamp() * 1000)
        if end is not None:
            params["endTime"] = int(end.timestamp() * 1000)

        path = "/api/v3/klines" if market_type == MarketType.SPOT else "/fapi/v1/klines"
        response = await self._get(base, path, params)
        rows = response.json()
        now = datetime.now(timezone.utc)
        candles: list[Candle] = []
        for row in rows:
            candle = normalize_binance_kline(
                row,
                exchange=self.exchange_id,
                symbol=internal,
                market_type=market_type,
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
        if timeframe not in BINANCE_INTERVALS:
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
            # Walk backward for additional history.
            cursor_end = previous_page_end(page[0])
            if start is not None and cursor_end <= start:
                break

        candles = sort_and_dedupe_candles(collected)[-target:]
        assert_homogeneous_series(candles)
        return candles

    @staticmethod
    def _ranking_volume(data: dict) -> float | None:
        """Prefer quoteVolume (USDT) for cross-pair liquidity ranking."""
        for key in ("quoteVolume", "quote_volume"):
            raw = data.get(key)
            if raw not in (None, ""):
                try:
                    return float(raw)
                except (TypeError, ValueError):
                    pass
        raw = data.get("volume")
        if raw not in (None, ""):
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None
        return None

    def _ticker_from_24hr(self, data: dict, market_type: MarketType) -> Ticker | None:
        native = data.get("symbol")
        if not native:
            return None
        last = data.get("lastPrice")
        if last in (None, ""):
            return None
        return Ticker(
            symbol=to_internal_symbol(str(native)),
            exchange=self.exchange_id,
            market_type=market_type,
            last=float(last),
            bid=float(data["bidPrice"]) if data.get("bidPrice") not in (None, "") else None,
            ask=float(data["askPrice"]) if data.get("askPrice") not in (None, "") else None,
            high_24h=float(data["highPrice"]) if data.get("highPrice") not in (None, "") else None,
            low_24h=float(data["lowPrice"]) if data.get("lowPrice") not in (None, "") else None,
            volume_24h=self._ranking_volume(data),
            change_pct_24h=(
                float(data["priceChangePercent"])
                if data.get("priceChangePercent") not in (None, "")
                else None
            ),
            updated_at=datetime.now(timezone.utc),
        )

    async def fetch_ticker(self, symbol: str, market_type: MarketType) -> Ticker:
        base = self._base_for(market_type)
        native = to_native_symbol(symbol)
        path = "/api/v3/ticker/24hr" if market_type == MarketType.SPOT else "/fapi/v1/ticker/24hr"
        response = await self._get(base, path, {"symbol": native})
        ticker = self._ticker_from_24hr(response.json(), market_type)
        if ticker is None:
            raise ExchangeRequestError(
                f"No Binance ticker for {native}",
                exchange=self.exchange_id.value,
                status_code=404,
            )
        return ticker

    async def fetch_tickers_24h(self, market_type: MarketType) -> list[Ticker]:
        """Single bulk 24hr ticker call for universe volume ranking."""
        self.ensure_market_type(market_type)
        base = self._base_for(market_type)
        path = "/api/v3/ticker/24hr" if market_type == MarketType.SPOT else "/fapi/v1/ticker/24hr"
        response = await self._get(base, path, {})
        payload = response.json()
        if not isinstance(payload, list):
            return []
        out: list[Ticker] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            ticker = self._ticker_from_24hr(item, market_type)
            if ticker is not None:
                out.append(ticker)
        return out
