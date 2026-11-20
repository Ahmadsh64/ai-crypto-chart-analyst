"""Locked trade-plan configuration (Phase 4.3)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.exchanges.types import Timeframe

STRATEGY_CONFIG_VERSION = "trade-plan-v1.0.0-balanced"

PlanDirection = Literal["bullish", "bearish"]
PlanStatus = Literal["eligible", "blocked", "invalid"]
EntryType = Literal["order_block", "fair_value_gap", "structure_retest", "market_condition"]


class TradePlanConfig(BaseModel):
    config_version: str = STRATEGY_CONFIG_VERSION

    # Eligibility (strong confluence only)
    min_directional_score: float = Field(default=70.0, ge=0, le=100)
    min_score_margin: float = Field(default=15.0, ge=0, le=100)
    require_assessment_strength: Literal["strong", "moderate", "any"] = "strong"
    block_critical_conflicts: bool = True
    required_timeframes: tuple[Timeframe, ...] = (
        Timeframe.H4,
        Timeframe.H1,
        Timeframe.M15,
    )
    setup_timeframe: Timeframe = Timeframe.M15
    confirmation_timeframe: Timeframe = Timeframe.M5
    liquidity_timeframes: tuple[Timeframe, ...] = (Timeframe.H1, Timeframe.M15)

    # Entry
    max_entry_distance_atr: float = Field(default=3.0, gt=0)
    allow_partially_active_zones: bool = True
    allow_structure_retest_entry: bool = True
    allow_market_condition_entry: bool = True
    """Market-condition entry only when price is already inside a valid directional zone."""

    # Stop loss
    atr_period: int = Field(default=14, ge=2, le=100)
    atr_buffer_mult: float = Field(default=0.25, ge=0)
    max_stop_distance_atr: float = Field(default=4.0, gt=0)
    min_stop_distance_atr: float = Field(default=0.15, gt=0)
    """Reject SL that sits inside the entry zone without this buffer beyond the invalidation edge."""

    # Take profit / RR
    minimum_primary_target_rr: float = Field(default=2.0, gt=0)
    max_targets: int = Field(default=3, ge=1, le=5)
    near_duplicate_pct: float = Field(default=0.001, gt=0, le=0.05)
    """Collapse targets within this relative distance of each other."""

    # Virtual sizing
    default_account_balance: float = Field(default=10_000.0, gt=0)
    default_risk_percent: float = Field(default=1.0, gt=0, le=100)
    max_risk_percent: float = Field(default=5.0, gt=0, le=100)
    min_account_balance: float = Field(default=1.0, gt=0)
    contract_multiplier: float = Field(default=1.0, gt=0)
    """Linear base-asset quantity model. Unavailable metadata → mark sizing unavailable."""

    @model_validator(mode="after")
    def _validate(self) -> "TradePlanConfig":
        if self.min_stop_distance_atr > self.max_stop_distance_atr:
            raise ValueError("min_stop_distance_atr must be ≤ max_stop_distance_atr")
        if self.default_risk_percent > self.max_risk_percent:
            raise ValueError("default_risk_percent must be ≤ max_risk_percent")
        return self

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


DEFAULT_TRADE_PLAN_CONFIG = TradePlanConfig()
