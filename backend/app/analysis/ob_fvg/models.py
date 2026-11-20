"""Typed Order Block and FVG models (Phase 3.4)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.exchanges.types import ExchangeId, MarketType, Timeframe


class ZoneSide(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class ObStatus(str, Enum):
    ACTIVE = "active"
    PARTIALLY_MITIGATED = "partially_mitigated"
    MITIGATED = "mitigated"
    INVALIDATED = "invalidated"


class FvgStatus(str, Enum):
    ACTIVE = "active"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    INVALIDATED = "invalidated"


class StructureSourceKind(str, Enum):
    BOS = "bos"
    MSS = "mss"


class OrderBlock(BaseModel):
    event_key: str
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    timeframe: Timeframe
    side: ZoneSide
    status: ObStatus
    zone_low: float
    zone_high: float
    boundary_method: str
    source_candle_timestamp: datetime
    source_open: float
    source_high: float
    source_low: float
    source_close: float
    source_structure_kind: StructureSourceKind
    source_structure_event_key: str
    structure_candle_timestamp: datetime
    detection_timestamp: datetime
    first_mitigation_timestamp: datetime | None = None
    full_mitigation_timestamp: datetime | None = None
    invalidation_timestamp: datetime | None = None
    config_version: str
    confirmed: bool = True
    segment_start: datetime | None = None
    segment_end: datetime | None = None
    segment_active: bool = True


class FairValueGap(BaseModel):
    event_key: str
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    timeframe: Timeframe
    side: ZoneSide
    status: FvgStatus
    zone_low: float
    zone_high: float
    gap_size: float
    candle1_timestamp: datetime
    candle2_timestamp: datetime
    candle3_timestamp: datetime
    candle1_high: float
    candle1_low: float
    candle3_high: float
    candle3_low: float
    detection_timestamp: datetime
    first_touch_timestamp: datetime | None = None
    max_fill_pct: float = 0.0
    full_fill_timestamp: datetime | None = None
    invalidation_timestamp: datetime | None = None
    config_version: str
    confirmed: bool = True
    segment_start: datetime | None = None
    segment_end: datetime | None = None
    segment_active: bool = True


class ObFvgSnapshot(BaseModel):
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    timeframe: Timeframe
    calculated_at: datetime
    config_version: str
    closed_candles_used: int
    active_ob_count: int
    active_fvg_count: int
    bullish_ob_count: int
    bearish_ob_count: int
    bullish_fvg_count: int
    bearish_fvg_count: int
    candle_range_start: datetime | None = None
    candle_range_end: datetime | None = None


class ObFvgResult(BaseModel):
    config: dict[str, Any]
    snapshot: ObFvgSnapshot
    bullish_order_blocks: list[OrderBlock] = Field(default_factory=list)
    bearish_order_blocks: list[OrderBlock] = Field(default_factory=list)
    bullish_fvgs: list[FairValueGap] = Field(default_factory=list)
    bearish_fvgs: list[FairValueGap] = Field(default_factory=list)
    provisional_order_blocks: list[OrderBlock] = Field(default_factory=list)
    provisional_fvgs: list[FairValueGap] = Field(default_factory=list)
    event_keys: list[str] = Field(default_factory=list)
