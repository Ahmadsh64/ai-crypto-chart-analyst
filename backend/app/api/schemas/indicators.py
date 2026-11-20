"""Indicator API response schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.analysis.indicators.models import IndicatorLatest, IndicatorSeriesResult, IndicatorStatus
from app.exchanges.types import ExchangeId, MarketType, Timeframe


class IndicatorsResponse(BaseModel):
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    timeframe: Timeframe
    calculated_at: datetime
    include_forming: bool
    closed_candles_used: int
    data_source: str
    indicators: dict[str, IndicatorLatest]
    series: dict[str, IndicatorSeriesResult] = Field(default_factory=dict)
    available_indicators: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IndicatorMetaItem(BaseModel):
    id: str
    params: dict[str, Any]
    warmup_required: int
    status_values: list[IndicatorStatus] = Field(
        default_factory=lambda: list(IndicatorStatus)
    )


class IndicatorsCatalogResponse(BaseModel):
    indicators: list[IndicatorMetaItem]
