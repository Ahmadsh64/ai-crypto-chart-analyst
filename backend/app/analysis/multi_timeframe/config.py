"""Locked Multi-Timeframe orchestration configuration (Phase 4.1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.exchanges.types import Timeframe

STRATEGY_CONFIG_VERSION = "mtf-v1.0.0-orchestration"

MTF_LADDER: tuple[Timeframe, ...] = (
    Timeframe.H4,
    Timeframe.H1,
    Timeframe.M15,
    Timeframe.M5,
)

TimeframePurpose = Literal[
    "htf_context",
    "market_structure",
    "setup",
    "entry_confirmation",
]

TIMEFRAME_PURPOSE: dict[Timeframe, TimeframePurpose] = {
    Timeframe.H4: "htf_context",
    Timeframe.H1: "market_structure",
    Timeframe.M15: "setup",
    Timeframe.M5: "entry_confirmation",
}

TIMEFRAME_DURATION_MINUTES: dict[Timeframe, int] = {
    Timeframe.H4: 240,
    Timeframe.H1: 60,
    Timeframe.M15: 15,
    Timeframe.M5: 5,
}


class TimeframeHistoryConfig(BaseModel):
    timeframe: Timeframe
    fetch_limit: int = Field(ge=50, le=2000)
    min_closed_candles: int = Field(ge=1, le=500)
    purpose: TimeframePurpose


class MultiTimeframeConfig(BaseModel):
    config_version: str = STRATEGY_CONFIG_VERSION
    timeframes: tuple[Timeframe, ...] = MTF_LADDER
    """How many timeframe intervals after the latest closed candle before marking stale."""
    stale_intervals: int = Field(default=3, ge=1, le=48)
    """Gap if adjacent open delta > gap_factor × expected step."""
    gap_factor: float = Field(default=1.5, gt=1.0, le=5.0)
    history: dict[str, TimeframeHistoryConfig] = Field(default_factory=dict)
    """Max closed candles echoed in REST/WS payload per TF (overview, not full dump)."""
    preview_closed_limit: int = Field(default=5, ge=0, le=50)

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def history_for(self, timeframe: Timeframe) -> TimeframeHistoryConfig:
        key = timeframe.value
        if key in self.history:
            return self.history[key]
        return DEFAULT_HISTORY[timeframe]


DEFAULT_HISTORY: dict[Timeframe, TimeframeHistoryConfig] = {
    Timeframe.H4: TimeframeHistoryConfig(
        timeframe=Timeframe.H4,
        fetch_limit=300,
        min_closed_candles=50,
        purpose="htf_context",
    ),
    Timeframe.H1: TimeframeHistoryConfig(
        timeframe=Timeframe.H1,
        fetch_limit=500,
        min_closed_candles=50,
        purpose="market_structure",
    ),
    Timeframe.M15: TimeframeHistoryConfig(
        timeframe=Timeframe.M15,
        fetch_limit=500,
        min_closed_candles=50,
        purpose="setup",
    ),
    Timeframe.M5: TimeframeHistoryConfig(
        timeframe=Timeframe.M5,
        fetch_limit=500,
        min_closed_candles=50,
        purpose="entry_confirmation",
    ),
}

DEFAULT_MTF_CONFIG = MultiTimeframeConfig(
    history={tf.value: cfg for tf, cfg in DEFAULT_HISTORY.items()},
)
