"""REST response schemas for Liquidity (Phase 3.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.analysis.liquidity.models import (
    AmbiguousLiquidityCross,
    EqualExtremeCluster,
    LiquidityLevel,
    LiquiditySnapshot,
    LiquiditySweep,
)
from app.exchanges.types import ExchangeId, MarketType, Timeframe


class LiquidityResponse(BaseModel):
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    timeframe: Timeframe
    calculated_at: datetime
    data_source: str
    include_unconfirmed: bool
    config: dict[str, Any]
    snapshot: LiquiditySnapshot
    eqh_clusters: list[EqualExtremeCluster] = Field(default_factory=list)
    eql_clusters: list[EqualExtremeCluster] = Field(default_factory=list)
    bsl_levels: list[LiquidityLevel] = Field(default_factory=list)
    ssl_levels: list[LiquidityLevel] = Field(default_factory=list)
    sweeps: list[LiquiditySweep] = Field(default_factory=list)
    provisional_sweeps: list[LiquiditySweep] = Field(default_factory=list)
    ambiguous_crosses: list[AmbiguousLiquidityCross] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
