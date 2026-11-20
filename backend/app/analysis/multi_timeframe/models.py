"""Pydantic models for Multi-Timeframe orchestration (Phase 4.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe

DataQuality = Literal["ok", "insufficient", "stale", "gaps", "error", "unavailable"]
OverallStatus = Literal["ready", "partial", "unavailable"]
GapSeverity = Literal["none", "minor", "major"]


class CandleGap(BaseModel):
    after_timestamp: datetime
    before_timestamp: datetime
    expected_seconds: int
    actual_seconds: float
    missing_estimate: int = Field(ge=0)


class TimeframeSeriesSummary(BaseModel):
    timeframe: Timeframe
    purpose: str
    duration_minutes: int
    latest_candle_time: datetime | None = None
    latest_closed_candle_time: datetime | None = None
    latest_price: float | None = None
    candles_count: int = 0
    closed_candles_count: int = 0
    is_ready: bool = False
    is_stale: bool = False
    has_data_gaps: bool = False
    data_quality: DataQuality = "unavailable"
    status_detail: str | None = None
    last_updated: datetime | None = None
    gap_count: int = 0
    gaps: list[CandleGap] = Field(default_factory=list)
    forming_candle: Candle | None = None
    """Bounded recent closed candles for overview (not full history)."""
    recent_closed_candles: list[Candle] = Field(default_factory=list)


class SyncMetadata(BaseModel):
    as_of: datetime
    note: str = (
        "Timeframes close independently; a closed lower-TF candle does not "
        "imply higher-TF confirmation."
    )
    latest_closed_by_timeframe: dict[str, datetime | None] = Field(default_factory=dict)
    forming_by_timeframe: dict[str, datetime | None] = Field(default_factory=dict)
    aligned: bool = False
    """True only when every ready TF has a closed candle (always true if ready)."""


class MultiTimeframeSnapshot(BaseModel):
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    calculated_at: datetime
    config_version: str
    overall_status: OverallStatus
    ready_timeframes: list[Timeframe] = Field(default_factory=list)
    unavailable_timeframes: list[Timeframe] = Field(default_factory=list)
    timeframes: list[TimeframeSeriesSummary] = Field(default_factory=list)
    sync: SyncMetadata
    metadata: dict[str, Any] = Field(default_factory=dict)
