"""Typed Market Structure event and snapshot models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.exchanges.types import ExchangeId, MarketType, Timeframe


class SwingKind(str, Enum):
    HIGH = "high"
    LOW = "low"


class StructureLabel(str, Enum):
    HH = "HH"
    LH = "LH"
    HL = "HL"
    LL = "LL"


class StructureBias(str, Enum):
    UNDEFINED = "undefined"
    BULLISH = "bullish"
    BEARISH = "bearish"


class StructureDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class BreakKind(str, Enum):
    BOS = "bos"
    CHOCH = "choch"


class SwingPoint(BaseModel):
    event_key: str
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    timeframe: Timeframe
    kind: SwingKind
    price: float
    candle_timestamp: datetime
    confirmation_timestamp: datetime
    confirmed: bool = True
    classification: StructureLabel | None = None
    previous_swing_key: str | None = None
    previous_swing_price: float | None = None
    config_version: str
    candle_index: int


class StructureBreak(BaseModel):
    """BOS or CHoCH break of a structure level (close confirmation)."""

    event_key: str
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    timeframe: Timeframe
    break_kind: BreakKind
    direction: StructureDirection
    broken_level: float
    broken_swing_key: str
    # Original swing candle open time (for swing→break chart segments).
    broken_swing_timestamp: datetime | None = None
    close_price: float
    candle_timestamp: datetime
    confirmation_timestamp: datetime
    previous_bias: StructureBias
    new_bias: StructureBias
    config_version: str
    candle_index: int
    body_size: float | None = None
    atr_value: float | None = None
    # Chart lifecycle metadata (optional; UI may prefer swing→break span).
    segment_start: datetime | None = None
    segment_end: datetime | None = None
    segment_active: bool = False


class AmbiguousDualBreak(BaseModel):
    """
    Diagnostic when one closed candle wicks through both active SH and SL
    but closes inside the structure range — no directional BOS/CHoCH/MSS.
    """

    event_key: str
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    timeframe: Timeframe
    candle_timestamp: datetime
    confirmation_timestamp: datetime
    close_price: float
    swing_high_level: float
    swing_low_level: float
    swing_high_key: str
    swing_low_key: str
    high: float
    low: float
    bias_unchanged: StructureBias
    config_version: str
    candle_index: int


class CHoCHEvent(BaseModel):
    event_key: str
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    timeframe: Timeframe
    direction: StructureDirection
    broken_level: float
    broken_swing_key: str
    close_price: float
    candle_timestamp: datetime
    confirmation_timestamp: datetime
    previous_bias: StructureBias
    new_bias: StructureBias
    config_version: str
    structure_break_key: str


class MSSEvent(BaseModel):
    event_key: str
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    timeframe: Timeframe
    direction: StructureDirection
    choch_event_key: str
    broken_level: float
    close_price: float
    candle_timestamp: datetime
    confirmation_timestamp: datetime
    body_size: float
    atr_value: float
    displacement_mult: float
    previous_bias: StructureBias
    new_bias: StructureBias
    config_version: str


class MarketStructureSnapshot(BaseModel):
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    timeframe: Timeframe
    bias: StructureBias
    latest_swing_high: SwingPoint | None = None
    latest_swing_low: SwingPoint | None = None
    # Preferred clear names: latest unbroken swing levels (break targets).
    active_unbroken_swing_high: float | None = Field(
        default=None,
        description=(
            "Price of the latest confirmed Swing High that has not yet been "
            "broken by a close. This is the bullish structure break *target* "
            "(not generic support)."
        ),
    )
    active_unbroken_swing_low: float | None = Field(
        default=None,
        description=(
            "Price of the latest confirmed Swing Low that has not yet been "
            "broken by a close. This is the bearish structure break *target* "
            "(not generic resistance)."
        ),
    )
    # Backward-compatible aliases (same values as unbroken SH/SL targets).
    active_bullish_level: float | None = Field(
        default=None,
        description="Alias of active_unbroken_swing_high (legacy field name).",
    )
    active_bearish_level: float | None = Field(
        default=None,
        description="Alias of active_unbroken_swing_low (legacy field name).",
    )
    last_bos_key: str | None = None
    last_choch_key: str | None = None
    last_mss_key: str | None = None
    last_ambiguous_dual_break_key: str | None = None
    closed_candles_used: int
    config_version: str
    calculated_at: datetime


class MarketStructureResult(BaseModel):
    config: dict[str, Any]
    snapshot: MarketStructureSnapshot
    swings: list[SwingPoint] = Field(default_factory=list)
    unconfirmed_swings: list[SwingPoint] = Field(default_factory=list)
    bos_events: list[StructureBreak] = Field(default_factory=list)
    choch_events: list[CHoCHEvent] = Field(default_factory=list)
    mss_events: list[MSSEvent] = Field(default_factory=list)
    ambiguous_dual_breaks: list[AmbiguousDualBreak] = Field(default_factory=list)
    event_keys: list[str] = Field(default_factory=list)
