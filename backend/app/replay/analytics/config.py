"""Performance analytics configuration (Phase 5.2.4).

Initial equity is OPTIONAL. Percentage / equity-based metrics are unavailable
when initial_equity is None. Never invent an account balance.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.replay.analytics.enums import DrawdownMode, EquityCurveMode, TimeGroupPeriod

ANALYTICS_VERSION = "performance-analytics-v1.0.0-balanced"


def _d(value: str | float | Decimal | None) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


class AnalyticsConfig(BaseModel):
    config_version: str = ANALYTICS_VERSION
    enabled: bool = False

    # Explicit capital — None means percentage/equity metrics unavailable.
    initial_equity: Decimal | None = None
    quote_currency: str = "USDT"

    # Inclusion policies
    include_closed_only_for_stats: bool = True
    include_partial_realized_in_cashflow: bool = True
    include_ambiguous_as_closed_when_flat: bool = True

    equity_curve_mode: EquityCurveMode = "completed_trade"
    drawdown_mode: DrawdownMode = "absolute_and_percent"
    time_group_period: TimeGroupPeriod = "daily"
    display_timezone: str = "UTC"

    group_by_symbol: bool = True
    group_by_timeframe: bool = True  # may be unavailable if trade lacks TF metadata
    group_by_direction: bool = True
    group_by_period: bool = True
    group_by_exit_type: bool = True

    disclaimer: str = (
        "HISTORICAL BACKTEST — SIMULATED RESULTS — NOT FINANCIAL ADVICE. "
        "Metrics derive from hypothetical historical simulation and estimated costs."
    )

    model_config = {"arbitrary_types_allowed": True}

    @field_validator("initial_equity", mode="before")
    @classmethod
    def coerce_equity(cls, v: Any) -> Any:
        return _d(v)

    @model_validator(mode="after")
    def validate_equity(self) -> AnalyticsConfig:
        if self.initial_equity is not None and self.initial_equity < 0:
            raise ValueError("initial_equity must be >= 0 when provided")
        return self

    def snapshot(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        if self.initial_equity is not None:
            data["initial_equity"] = format(self.initial_equity, "f")
        return data


def default_analytics_config() -> AnalyticsConfig:
    return AnalyticsConfig()


DEFAULT_ANALYTICS_CONFIG = AnalyticsConfig()
