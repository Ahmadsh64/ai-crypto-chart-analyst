"""Typed Liquidity event and snapshot models (Phase 3.3.1)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.exchanges.types import ExchangeId, MarketType, Timeframe


class LiquidityType(str, Enum):
    BSL = "bsl"
    SSL = "ssl"


class LiquiditySourceType(str, Enum):
    SWING = "swing"
    EQH = "eqh"
    EQL = "eql"


class LiquidityStatus(str, Enum):
    ACTIVE = "active"
    SWEPT = "swept"
    BROKEN = "broken"
    INVALIDATED = "invalidated"  # reserved — never assigned in liq-v1.1.0-balanced


class SweepDirection(str, Enum):
    """
    DEPRECATED liquidity-*side* label (Phase 3.3).

    Retained for API backward compatibility. Prefer `liquidity_type` (authoritative
    pool) and `reaction_hint` (contextual ICT reaction, not a trade signal).
    """

    BULLISH_SIDE = "bullish_side"  # historically: BSL sweep (side, not reaction)
    BEARISH_SIDE = "bearish_side"  # historically: SSL sweep (side, not reaction)


class ReactionHint(str, Enum):
    """
    Contextual ICT reaction interpretation after a confirmed sweep.

    NOT a guaranteed reversal and NOT a trade signal.
    """

    BULLISH = "bullish"
    BEARISH = "bearish"


class SwingContribution(BaseModel):
    swing_key: str
    price: float
    candle_timestamp: datetime
    confirmation_timestamp: datetime


class EqualExtremeCluster(BaseModel):
    event_key: str
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    timeframe: Timeframe
    kind: str  # "eqh" | "eql"
    level: float = Field(
        description="Representative median of member prices (backward-compatible alias).",
    )
    representative_level: float = Field(
        description="Median of member prices — same value as `level`.",
    )
    min_price: float
    max_price: float
    price_range: float
    members: list[SwingContribution]
    member_count: int
    first_detection_timestamp: datetime
    latest_confirmation_timestamp: datetime
    config_version: str
    tolerance_used: float
    atr_available: bool


class LiquidityLevel(BaseModel):
    event_key: str
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    timeframe: Timeframe
    liquidity_type: LiquidityType
    source_type: LiquiditySourceType
    price: float
    status: LiquidityStatus
    source_swing_keys: list[str]
    source_swings: list[SwingContribution]
    cluster_key: str | None = None
    detection_timestamp: datetime
    latest_confirmation_timestamp: datetime
    status_changed_timestamp: datetime | None = None
    config_version: str
    segment_start: datetime | None = None
    segment_end: datetime | None = None
    segment_active: bool = True


class LiquiditySweep(BaseModel):
    event_key: str
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    timeframe: Timeframe
    direction: SweepDirection = Field(
        description="DEPRECATED side label. Use liquidity_type + reaction_hint.",
    )
    reaction_hint: ReactionHint | None = Field(
        default=None,
        description=(
            "Contextual ICT reaction (bearish after BSL sweep, bullish after SSL sweep). "
            "Null when unavailable. Not a trade signal."
        ),
    )
    liquidity_level_key: str
    liquidity_type: LiquidityType
    level_price: float
    wick_extreme: float
    close_price: float
    penetration: float
    candle_timestamp: datetime
    confirmation_timestamp: datetime
    confirmed: bool
    config_version: str
    candle_index: int


class AmbiguousLiquidityCross(BaseModel):
    event_key: str
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    timeframe: Timeframe
    candle_timestamp: datetime
    confirmation_timestamp: datetime
    close_price: float
    high: float
    low: float
    bsl_level_keys: list[str]
    ssl_level_keys: list[str]
    config_version: str
    reaction_hint: ReactionHint | None = None  # always null when emitted


class LiquiditySnapshot(BaseModel):
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    timeframe: Timeframe
    calculated_at: datetime
    config_version: str
    closed_candles_used: int
    active_bsl_count: int
    active_ssl_count: int
    eqh_count: int
    eql_count: int
    sweep_count: int
    candle_range_start: datetime | None = None
    candle_range_end: datetime | None = None


class LiquidityResult(BaseModel):
    config: dict[str, Any]
    snapshot: LiquiditySnapshot
    eqh_clusters: list[EqualExtremeCluster] = Field(default_factory=list)
    eql_clusters: list[EqualExtremeCluster] = Field(default_factory=list)
    bsl_levels: list[LiquidityLevel] = Field(default_factory=list)
    ssl_levels: list[LiquidityLevel] = Field(default_factory=list)
    sweeps: list[LiquiditySweep] = Field(default_factory=list)
    provisional_sweeps: list[LiquiditySweep] = Field(default_factory=list)
    ambiguous_crosses: list[AmbiguousLiquidityCross] = Field(default_factory=list)
    event_keys: list[str] = Field(default_factory=list)
