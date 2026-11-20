"""API schemas for Market Structure responses."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.analysis.market_structure.models import (
    AmbiguousDualBreak,
    CHoCHEvent,
    MarketStructureSnapshot,
    MSSEvent,
    StructureBreak,
    SwingPoint,
)
from app.exchanges.types import ExchangeId, MarketType, Timeframe


class MarketStructureResponse(BaseModel):
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    timeframe: Timeframe
    calculated_at: datetime
    data_source: str
    include_unconfirmed: bool
    config: dict[str, Any]
    snapshot: MarketStructureSnapshot
    swings: list[SwingPoint] = Field(default_factory=list)
    unconfirmed_swings: list[SwingPoint] = Field(default_factory=list)
    bos_events: list[StructureBreak] = Field(default_factory=list)
    choch_events: list[CHoCHEvent] = Field(default_factory=list)
    mss_events: list[MSSEvent] = Field(default_factory=list)
    ambiguous_dual_breaks: list[AmbiguousDualBreak] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
