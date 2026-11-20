"""Locked final-decision configuration (Phase 4.4)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.exchanges.types import Timeframe

STRATEGY_CONFIG_VERSION = "decision-v1.0.0-balanced"

FinalDecision = Literal["LONG", "SHORT", "WAIT", "NO TRADE"]
SetupLifecycle = Literal[
    "setup_detected",
    "awaiting_confirmation",
    "entry_confirmed",
    "invalidated",
    "expired",
]
EntryConfirmationStatus = Literal[
    "confirmed",
    "not_confirmed",
    "unavailable",
    "conflicted",
]


class DecisionConfig(BaseModel):
    config_version: str = STRATEGY_CONFIG_VERSION

    # Align with strong confluence / trade-plan gates
    min_directional_score: float = Field(default=70.0, ge=0, le=100)
    min_score_margin: float = Field(default=15.0, ge=0, le=100)
    require_assessment_strength: Literal["strong", "moderate", "any"] = "strong"
    minimum_primary_rr: float = Field(default=2.0, gt=0)
    block_critical_conflicts: bool = True

    required_timeframes: tuple[Timeframe, ...] = (
        Timeframe.H4,
        Timeframe.H1,
        Timeframe.M15,
        Timeframe.M5,
    )
    confirmation_timeframe: Timeframe = Timeframe.M5
    setup_timeframe: Timeframe = Timeframe.M15

    # Entry trigger
    require_price_inside_entry_zone: bool = True
    """LONG/SHORT require current price inside the planned entry zone."""
    require_5m_confirmation: bool = True
    max_confirmation_age_candles: int = Field(default=6, ge=1, le=50)
    """Confirmation event must be within this many closed 5M candles of now."""

    # Lifecycle / expiration (setup TF closed candles since plan source timestamp)
    max_setup_age_candles: int = Field(default=16, ge=1, le=200)
    """15M closed candles after entry source_timestamp before setup expires."""
    max_setup_age_hours: float = Field(default=12.0, gt=0)

    # Spot policy
    spot_allow_long: bool = True
    spot_allow_short: bool = False
    """If False, Spot never emits SHORT; confirmed bearish Spot → NO TRADE."""

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


DEFAULT_DECISION_CONFIG = DecisionConfig()
