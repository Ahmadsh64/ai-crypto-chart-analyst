"""REST response schemas for Multi-Timeframe orchestration (Phase 4.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.analysis.multi_timeframe.models import (
    MultiTimeframeSnapshot,
    SyncMetadata,
    TimeframeSeriesSummary,
)
from app.exchanges.types import ExchangeId, MarketType


class MultiTimeframeResponse(BaseModel):
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    calculated_at: datetime
    data_source: str
    config: dict[str, Any]
    snapshot: MultiTimeframeSnapshot
    timeframes: list[TimeframeSeriesSummary] = Field(default_factory=list)
    sync: SyncMetadata
    metadata: dict[str, Any] = Field(default_factory=dict)
