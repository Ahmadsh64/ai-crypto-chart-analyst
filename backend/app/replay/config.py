"""Historical replay configuration (Phase 5.1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.exchanges.types import Timeframe

STRATEGY_CONFIG_VERSION = "replay-v1.0.0"

REPLAY_TIMEFRAMES: tuple[Timeframe, ...] = (
    Timeframe.H4,
    Timeframe.H1,
    Timeframe.M15,
    Timeframe.M5,
)

ReplaySpeed = Literal["1x", "2x", "5x", "10x", "50x", "100x", "max"]
ReplayStatus = Literal[
    "created",
    "loading",
    "ready",
    "running",
    "paused",
    "completed",
    "stopped",
    "error",
]

# Wall-clock sleep between events when status=running (pacing only).
SPEED_DELAY_SECONDS: dict[str, float] = {
    "1x": 1.0,
    "2x": 0.5,
    "5x": 0.2,
    "10x": 0.1,
    "50x": 0.02,
    "100x": 0.01,
    "max": 0.0,
}


class ReplayConfig(BaseModel):
    config_version: str = STRATEGY_CONFIG_VERSION
    timeframes: tuple[Timeframe, ...] = REPLAY_TIMEFRAMES
    """Base event TF — every higher-TF close aligns to a 5M close."""
    event_timeframe: Timeframe = Timeframe.M5
    max_candles_per_timeframe: int = Field(default=5000, ge=100, le=50_000)
    preview_closed_limit: int = Field(default=200, ge=10, le=2000)
    default_speed: ReplaySpeed = "10x"

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


DEFAULT_REPLAY_CONFIG = ReplayConfig()
