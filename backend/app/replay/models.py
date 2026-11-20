"""Replay session and snapshot models (Phase 5.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.replay.config import ReplaySpeed, ReplayStatus


class CandleGapInfo(BaseModel):
    timeframe: Timeframe
    after_open: datetime
    before_open: datetime
    missing_estimate: int


class TimeframeReplayState(BaseModel):
    timeframe: Timeframe
    closed_candles: list[Candle] = Field(default_factory=list)
    """Bounded recent closed candles visible at replay clock (no future)."""
    closed_count: int = 0
    forming_candle: Candle | None = None
    latest_closed_open_time: datetime | None = None
    latest_closed_close_time: datetime | None = None
    latest_price: float | None = None
    is_ready: bool = False
    data_quality: Literal["ok", "insufficient", "gaps", "empty"] = "empty"
    gap_count: int = 0


class ReplaySnapshot(BaseModel):
    session_id: str
    replay_timestamp: datetime
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    event_index: int
    event_count: int
    progress_pct: float
    status: ReplayStatus
    speed: ReplaySpeed
    timeframes: dict[str, TimeframeReplayState] = Field(default_factory=dict)
    gaps: list[CandleGapInfo] = Field(default_factory=list)
    data_quality: Literal["ok", "partial", "insufficient", "empty"] = "empty"
    limitations: list[str] = Field(default_factory=list)
    config_version: str
    """Candle timestamps are open times (UTC). Close = open + TF duration − 1ms."""
    timestamp_convention: str = "open_time_utc"


class ReplaySessionInfo(BaseModel):
    session_id: str
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    start_time: datetime
    end_time: datetime
    timeframes: list[Timeframe]
    status: ReplayStatus
    speed: ReplaySpeed
    event_index: int
    event_count: int
    replay_timestamp: datetime | None = None
    created_at: datetime
    error: str | None = None
    config_version: str
    data_quality: str = "empty"
    limitations: list[str] = Field(default_factory=list)


class ReplayEventPayload(BaseModel):
    type: str
    session_id: str
    replay_timestamp: datetime | None = None
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    timeframe: Timeframe | None = None
    status: ReplayStatus | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
