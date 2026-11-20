"""Performance analytics models (Phase 5.2.4)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.replay.analytics.enums import MetricAvailability


def _ser_dec(v: Decimal | None) -> str | None:
    if v is None:
        return None
    return format(v, "f")


class MetricValue(BaseModel):
    """Typed metric that can be unavailable without lying as zero."""

    value: Decimal | None = None
    availability: MetricAvailability = "available"
    label: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    def public_dict(self) -> dict[str, Any]:
        return {
            "value": _ser_dec(self.value) if self.availability == "available" else None,
            "availability": self.availability,
            "label": self.label,
        }


class TradeStatistics(BaseModel):
    total_simulated_trades: int = 0
    completed_trades: int = 0
    open_trades: int = 0
    partially_closed_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    break_even_trades: int = 0
    win_rate: MetricValue = Field(default_factory=lambda: MetricValue(availability="unavailable"))
    loss_rate: MetricValue = Field(default_factory=lambda: MetricValue(availability="unavailable"))
    average_winning_trade: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    average_losing_trade: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    largest_winning_trade: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    largest_losing_trade: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )


class ProfitabilityMetrics(BaseModel):
    total_gross_realized_pnl: Decimal = Decimal("0")
    total_net_realized_pnl: Decimal = Decimal("0")
    total_trading_fees: Decimal = Decimal("0")
    total_slippage: Decimal = Decimal("0")
    total_spread_costs: Decimal = Decimal("0")
    total_execution_costs: Decimal = Decimal("0")
    average_net_pnl_per_completed: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    profit_factor: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    gross_profit: Decimal = Decimal("0")
    gross_loss: Decimal = Decimal("0")

    model_config = {"arbitrary_types_allowed": True}


class RiskRewardMetrics(BaseModel):
    average_r_multiple: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    median_r_multiple: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    best_r_multiple: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    worst_r_multiple: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    avg_win_loss_ratio: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    r_multiple_sample_count: int = 0
    missing_risk_metadata_count: int = 0


class ReturnMetrics(BaseModel):
    initial_equity: Decimal | None = None
    current_equity: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    ending_equity: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    total_return_pct: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    average_trade_return_pct: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    best_trade_return_pct: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    worst_trade_return_pct: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )

    model_config = {"arbitrary_types_allowed": True}


class EquityPoint(BaseModel):
    timestamp: datetime
    trade_id: str
    event_id: str | None = None
    net_pnl_change: Decimal
    cumulative_net_pnl: Decimal
    equity: Decimal | None = None
    completed_trade_count: int = 0
    curve: str  # completed_trade | realized_cashflow

    model_config = {"arbitrary_types_allowed": True}


class EquityCurve(BaseModel):
    mode: str
    points: list[EquityPoint] = Field(default_factory=list)
    available: bool = True
    unavailable_reason: str | None = None
    initial_equity: Decimal | None = None
    ending_equity: Decimal | None = None
    cumulative_net_pnl: Decimal = Decimal("0")

    model_config = {"arbitrary_types_allowed": True}


class DrawdownPoint(BaseModel):
    timestamp: datetime
    equity: Decimal | None = None
    peak_equity: Decimal | None = None
    drawdown: Decimal
    drawdown_pct: Decimal | None = None

    model_config = {"arbitrary_types_allowed": True}


class DrawdownSummary(BaseModel):
    available: bool = True
    unavailable_reason: str | None = None
    absolute_drawdown: Decimal = Decimal("0")
    drawdown_pct: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    max_drawdown: Decimal = Decimal("0")
    max_drawdown_pct: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    peak_timestamp: datetime | None = None
    trough_timestamp: datetime | None = None
    recovery_timestamp: datetime | None = None
    current_drawdown: Decimal = Decimal("0")
    current_drawdown_pct: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    series: list[DrawdownPoint] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}


class GroupPerformanceRow(BaseModel):
    key: str
    completed_trades: int = 0
    win_rate: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    net_pnl: Decimal = Decimal("0")
    profit_factor: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    average_net_trade: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )
    average_r_multiple: MetricValue = Field(
        default_factory=lambda: MetricValue(availability="unavailable")
    )

    model_config = {"arbitrary_types_allowed": True}


class PerformanceGroups(BaseModel):
    by_symbol: list[GroupPerformanceRow] = Field(default_factory=list)
    by_timeframe: list[GroupPerformanceRow] = Field(default_factory=list)
    by_direction: list[GroupPerformanceRow] = Field(default_factory=list)
    by_period: list[GroupPerformanceRow] = Field(default_factory=list)
    by_exit_type: list[GroupPerformanceRow] = Field(default_factory=list)
    timeframe_unavailable_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class AnalyticsTradeRow(BaseModel):
    trade_id: str
    symbol: str
    direction: str
    lifecycle_status: str
    analytics_class: str
    exit_type: str
    net_realized_pnl: Decimal | None = None
    gross_realized_pnl: Decimal | None = None
    r_multiple: Decimal | None = None
    entry_timestamp: datetime | None = None
    exit_timestamp: datetime | None = None
    included_in_completed_stats: bool = False

    model_config = {"arbitrary_types_allowed": True}


class PerformanceSummary(BaseModel):
    session_id: str
    enabled: bool
    analytics_version: str
    cost_model_version: str | None = None
    replay_timestamp: datetime | None = None
    event_index: int | None = None
    quote_currency: str = "USDT"
    initial_equity: Decimal | None = None
    initial_equity_source: str = "not_configured"
    trade_stats: TradeStatistics = Field(default_factory=TradeStatistics)
    profitability: ProfitabilityMetrics = Field(default_factory=ProfitabilityMetrics)
    risk_reward: RiskRewardMetrics = Field(default_factory=RiskRewardMetrics)
    returns: ReturnMetrics = Field(default_factory=ReturnMetrics)
    drawdown: DrawdownSummary = Field(default_factory=DrawdownSummary)
    included_completed_trades: int = 0
    excluded_open_trades: int = 0
    excluded_partial_trades: int = 0
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = ""
    filter_context: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


class AnalyticsSnapshot(BaseModel):
    session_id: str
    enabled: bool
    analytics_version: str
    summary: PerformanceSummary
    equity_completed: EquityCurve
    equity_cashflow: EquityCurve
    drawdown: DrawdownSummary
    groups: PerformanceGroups
    completed_trades: list[AnalyticsTradeRow] = Field(default_factory=list)
    disclaimer: str
