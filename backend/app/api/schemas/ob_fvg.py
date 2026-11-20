"""REST response schemas for Order Blocks / FVG (Phase 3.4)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.analysis.ob_fvg.models import FairValueGap, ObFvgSnapshot, OrderBlock
from app.exchanges.types import ExchangeId, MarketType, Timeframe


class ObFvgResponse(BaseModel):
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    timeframe: Timeframe
    calculated_at: datetime
    data_source: str
    include_unconfirmed: bool
    config: dict[str, Any]
    snapshot: ObFvgSnapshot
    bullish_order_blocks: list[OrderBlock] = Field(default_factory=list)
    bearish_order_blocks: list[OrderBlock] = Field(default_factory=list)
    bullish_fvgs: list[FairValueGap] = Field(default_factory=list)
    bearish_fvgs: list[FairValueGap] = Field(default_factory=list)
    provisional_order_blocks: list[OrderBlock] = Field(default_factory=list)
    provisional_fvgs: list[FairValueGap] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
