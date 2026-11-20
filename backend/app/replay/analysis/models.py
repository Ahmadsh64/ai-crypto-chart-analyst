"""Historical analysis snapshot models (Phase 5.2.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.exchanges.types import ExchangeId, MarketType, Timeframe


class IndicatorLatestSummary(BaseModel):
    timeframe: Timeframe
    values: dict[str, float | None] = Field(default_factory=dict)
    statuses: dict[str, str] = Field(default_factory=dict)
    closed_candles_used: int = 0
    warming_up: bool = False


class StructureSummary(BaseModel):
    timeframe: Timeframe
    bias: str | None = None
    swing_count: int = 0
    bos_count: int = 0
    choch_count: int = 0
    mss_count: int = 0
    latest_event: str | None = None


class LiquiditySummary(BaseModel):
    timeframe: Timeframe
    eqh_count: int = 0
    eql_count: int = 0
    bsl_count: int = 0
    ssl_count: int = 0
    sweep_count: int = 0
    latest_sweep: str | None = None


class ObFvgSummary(BaseModel):
    timeframe: Timeframe
    bullish_ob_count: int = 0
    bearish_ob_count: int = 0
    bullish_fvg_count: int = 0
    bearish_fvg_count: int = 0
    active_zone_count: int = 0


class HistoricalAnalysisSnapshot(BaseModel):
    """Compact immutable analysis result at one replay timestamp."""

    session_id: str
    replay_timestamp: datetime
    event_index: int
    exchange: ExchangeId
    symbol: str
    market_type: MarketType

    decision: str
    decision_reason: str
    lifecycle_status: str
    direction: str | None = None

    bullish_score: float
    bearish_score: float
    confluence_strength: str | None = None
    preliminary_assessment: str | None = None
    conflicts: list[str] = Field(default_factory=list)
    evidence_summary: list[str] = Field(default_factory=list)

    entry_zone: dict[str, Any] | None = None
    stop_loss: float | None = None
    take_profit_levels: list[float] = Field(default_factory=list)
    risk_reward: float | None = None
    trade_plan_status: str | None = None
    position_size: float | None = None
    expires_at: datetime | None = None
    decision_id: str | None = None
    trade_plan_id: str | None = None
    hypothetical_plan_disclaimer: str = (
        "Hypothetical analytical plan only — no fills, fees, or P&L simulated."
    )

    indicators: dict[str, IndicatorLatestSummary] = Field(default_factory=dict)
    structure: dict[str, StructureSummary] = Field(default_factory=dict)
    liquidity: dict[str, LiquiditySummary] = Field(default_factory=dict)
    ob_fvg: dict[str, ObFvgSummary] = Field(default_factory=dict)

    closed_candle_counts: dict[str, int] = Field(default_factory=dict)
    data_quality: str = "unknown"
    data_ready: bool = False
    limitations: list[str] = Field(default_factory=list)
    analysis_versions: dict[str, str] = Field(default_factory=dict)
    analysis_error: str | None = None
    config_version: str
    analysis_timestamp: datetime
    timestamp_convention: str = "open_time_utc"
    kind: Literal["historical_analysis"] = "historical_analysis"


class HistoricalAnalysisHistoryResponse(BaseModel):
    session_id: str
    count: int
    offset: int
    limit: int
    total: int
    snapshots: list[HistoricalAnalysisSnapshot]
