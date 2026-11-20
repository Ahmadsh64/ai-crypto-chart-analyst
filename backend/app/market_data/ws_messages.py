"""Normalized WebSocket market messages and exchange payload parsers."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.market_data.normalizer import to_internal_symbol

BYBIT_INTERVAL: dict[Timeframe, str] = {
    Timeframe.M1: "1",
    Timeframe.M5: "5",
    Timeframe.M15: "15",
    Timeframe.M30: "30",
    Timeframe.H1: "60",
    Timeframe.H4: "240",
    Timeframe.D1: "D",
}

BINANCE_INTERVAL: dict[Timeframe, str] = {
    Timeframe.M1: "1m",
    Timeframe.M5: "5m",
    Timeframe.M15: "15m",
    Timeframe.M30: "30m",
    Timeframe.H1: "1h",
    Timeframe.H4: "4h",
    Timeframe.D1: "1d",
}


class WsMessageType(str, Enum):
    TICKER_UPDATE = "ticker_update"
    TRADE_UPDATE = "trade_update"
    CANDLE_UPDATE = "candle_update"
    INDICATOR_UPDATE = "indicator_update"
    STRUCTURE_UPDATE = "structure_update"
    LIQUIDITY_UPDATE = "liquidity_update"
    OB_FVG_UPDATE = "ob_fvg_update"
    MULTI_TIMEFRAME_UPDATE = "multi_timeframe_update"
    CONFLUENCE_UPDATE = "confluence_update"
    TRADE_PLAN_UPDATE = "trade_plan_update"
    DECISION_UPDATE = "decision_update"
    CONNECTION_STATUS = "connection_status"
    SUBSCRIPTION_ERROR = "subscription_error"
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"


class TickerData(BaseModel):
    last: float
    bid: float | None = None
    ask: float | None = None
    high_24h: float | None = None
    low_24h: float | None = None
    volume_24h: float | None = None
    change_pct_24h: float | None = None


class TradeData(BaseModel):
    price: float
    quantity: float
    side: Literal["buy", "sell", "unknown"] = "unknown"
    trade_id: str | None = None


class CandleData(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_closed: bool
    timeframe: Timeframe


class MarketWsMessage(BaseModel):
    type: WsMessageType
    exchange: ExchangeId | None = None
    symbol: str | None = None
    market_type: MarketType | None = None
    timeframe: Timeframe | None = None
    exchange_ts: datetime | None = Field(
        default=None, description="Timestamp from the exchange payload (UTC)"
    )
    processed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Local processing timestamp (UTC)",
    )
    status: str | None = None
    detail: str | None = None
    data: dict[str, Any] | TickerData | TradeData | CandleData | None = None


def _ms_to_dt(ms: int | float | str | None) -> datetime | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)


def parse_binance_payload(
    payload: dict[str, Any],
    *,
    market_type: MarketType,
) -> MarketWsMessage | None:
    """Parse a Binance raw or combined-stream payload into a normalized message."""
    data = payload.get("data") if "data" in payload and isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        return None

    event = data.get("e")
    symbol = to_internal_symbol(str(data.get("s") or ""))
    exchange_ts = _ms_to_dt(data.get("E"))

    if event == "24hrTicker" or (event is None and "c" in data and "P" in data and "s" in data):
        return MarketWsMessage(
            type=WsMessageType.TICKER_UPDATE,
            exchange=ExchangeId.BINANCE,
            symbol=symbol,
            market_type=market_type,
            exchange_ts=exchange_ts,
            data=TickerData(
                last=float(data["c"]),
                bid=float(data["b"]) if data.get("b") not in (None, "") else None,
                ask=float(data["a"]) if data.get("a") not in (None, "") else None,
                high_24h=float(data["h"]) if data.get("h") not in (None, "") else None,
                low_24h=float(data["l"]) if data.get("l") not in (None, "") else None,
                volume_24h=float(data["v"]) if data.get("v") not in (None, "") else None,
                change_pct_24h=float(data["P"]) if data.get("P") not in (None, "") else None,
            ),
        )

    if event == "trade":
        return MarketWsMessage(
            type=WsMessageType.TRADE_UPDATE,
            exchange=ExchangeId.BINANCE,
            symbol=symbol,
            market_type=market_type,
            exchange_ts=exchange_ts or _ms_to_dt(data.get("T")),
            data=TradeData(
                price=float(data["p"]),
                quantity=float(data["q"]),
                side="sell" if data.get("m") else "buy",
                trade_id=str(data.get("t")) if data.get("t") is not None else None,
            ),
        )

    if event == "kline":
        k = data.get("k") or {}
        interval = str(k.get("i") or "")
        timeframe = next((tf for tf, val in BINANCE_INTERVAL.items() if val == interval), None)
        return MarketWsMessage(
            type=WsMessageType.CANDLE_UPDATE,
            exchange=ExchangeId.BINANCE,
            symbol=to_internal_symbol(str(k.get("s") or symbol)),
            market_type=market_type,
            timeframe=timeframe,
            exchange_ts=exchange_ts,
            data=CandleData(
                timestamp=_ms_to_dt(k["t"]) or datetime.now(timezone.utc),
                open=float(k["o"]),
                high=float(k["h"]),
                low=float(k["l"]),
                close=float(k["c"]),
                volume=float(k["v"]),
                is_closed=bool(k.get("x")),
                timeframe=timeframe or Timeframe.M1,
            ),
        )

    return None


def parse_bybit_payload(
    payload: dict[str, Any],
    *,
    market_type: MarketType,
) -> list[MarketWsMessage]:
    """Parse a Bybit public WS payload into zero or more normalized messages."""
    topic = str(payload.get("topic") or "")
    ts = _ms_to_dt(payload.get("ts"))
    data = payload.get("data")
    messages: list[MarketWsMessage] = []

    if topic.startswith("tickers."):
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            symbol = to_internal_symbol(str(item.get("symbol") or topic.split(".", 1)[-1]))
            last = item.get("lastPrice")
            if last in (None, ""):
                continue
            change = item.get("price24hPcnt")
            change_pct = float(change) * 100 if change not in (None, "") else None
            messages.append(
                MarketWsMessage(
                    type=WsMessageType.TICKER_UPDATE,
                    exchange=ExchangeId.BYBIT,
                    symbol=symbol,
                    market_type=market_type,
                    exchange_ts=ts,
                    data=TickerData(
                        last=float(last),
                        bid=float(item["bid1Price"]) if item.get("bid1Price") not in (None, "") else None,
                        ask=float(item["ask1Price"]) if item.get("ask1Price") not in (None, "") else None,
                        high_24h=float(item["highPrice24h"]) if item.get("highPrice24h") not in (None, "") else None,
                        low_24h=float(item["lowPrice24h"]) if item.get("lowPrice24h") not in (None, "") else None,
                        volume_24h=float(item["volume24h"]) if item.get("volume24h") not in (None, "") else None,
                        change_pct_24h=change_pct,
                    ),
                )
            )
        return messages

    if topic.startswith("publicTrade."):
        items = data if isinstance(data, list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            side_raw = str(item.get("S") or "").lower()
            side: Literal["buy", "sell", "unknown"] = (
                "buy" if side_raw == "buy" else "sell" if side_raw == "sell" else "unknown"
            )
            messages.append(
                MarketWsMessage(
                    type=WsMessageType.TRADE_UPDATE,
                    exchange=ExchangeId.BYBIT,
                    symbol=to_internal_symbol(str(item.get("s") or topic.split(".", 1)[-1])),
                    market_type=market_type,
                    exchange_ts=_ms_to_dt(item.get("T")) or ts,
                    data=TradeData(
                        price=float(item["p"]),
                        quantity=float(item["v"]),
                        side=side,
                        trade_id=str(item.get("i")) if item.get("i") is not None else None,
                    ),
                )
            )
        return messages

    if topic.startswith("kline."):
        parts = topic.split(".")
        interval = parts[1] if len(parts) > 1 else ""
        timeframe = next((tf for tf, val in BYBIT_INTERVAL.items() if val == interval), None)
        items = data if isinstance(data, list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            symbol = to_internal_symbol(parts[2] if len(parts) > 2 else "")
            messages.append(
                MarketWsMessage(
                    type=WsMessageType.CANDLE_UPDATE,
                    exchange=ExchangeId.BYBIT,
                    symbol=symbol,
                    market_type=market_type,
                    timeframe=timeframe,
                    exchange_ts=ts or _ms_to_dt(item.get("timestamp")),
                    data=CandleData(
                        timestamp=_ms_to_dt(item.get("start")) or datetime.now(timezone.utc),
                        open=float(item["open"]),
                        high=float(item["high"]),
                        low=float(item["low"]),
                        close=float(item["close"]),
                        volume=float(item["volume"]),
                        is_closed=bool(item.get("confirm")),
                        timeframe=timeframe or Timeframe.M1,
                    ),
                )
            )
        return messages

    return messages
