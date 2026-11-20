"""Backtesting report snapshot models (Phase 5.2.6).

The report is a read-only assembler: it reuses analytics / simulation / costs
state and never reinvents metrics. Metric availability semantics from
``MetricValue`` are preserved.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.replay.analytics.enums import MetricAvailability
from app.replay.analytics.models import (
    DrawdownPoint,
    DrawdownSummary,
    EquityCurve,
    MetricValue,
    PerformanceGroups,
    PerformanceSummary,
)


# ─── Metadata ───


class ReportMetadata(BaseModel):
    report_id: str
    report_version: str
    session_id: str
    generated_at: datetime
    replay_timestamp: datetime | None = None
    event_index: int | None = None
    event_count: int | None = None
    exchange: ExchangeId
    symbol: str
    market_type: MarketType
    timeframes: list[Timeframe] = Field(default_factory=list)
    replay_start: datetime | None = None
    replay_end: datetime | None = None
    status: str | None = None
    data_quality: str | None = None
    initial_equity: Decimal | None = None
    initial_equity_source: str | None = None
    quote_currency: str = "USDT"
    disclaimer: str
    filter_context: dict[str, Any] = Field(default_factory=dict)
    cost_model_version: str | None = None
    analytics_version: str | None = None

    model_config = {"arbitrary_types_allowed": True}


# ─── Trade rows ───


class ReportTradeDetail(BaseModel):
    """Enriched completed-trade row joining analytics + sim + costs.

    ``average_exit_price`` is derived as the quantity-weighted VWAP of exit
    ledger fills for the trade. It is ``None`` (not zero) when no exit fills
    exist in the ledger.
    """

    trade_id: str
    symbol: str
    direction: str
    lifecycle_status: str
    analytics_class: str
    exit_type: str
    included_in_completed_stats: bool

    entry_timestamp: datetime | None = None
    exit_timestamp: datetime | None = None

    entry_price: Decimal | None = None
    average_exit_price: Decimal | None = None
    average_exit_price_source: str = "ledger_vwap"

    original_quantity: Decimal | None = None
    executed_quantity: Decimal | None = None
    remaining_quantity: Decimal | None = None

    initial_stop_loss: Decimal | None = None
    current_stop_loss: Decimal | None = None
    take_profit_levels: list[Decimal] = Field(default_factory=list)

    gross_realized_pnl: Decimal | None = None
    net_realized_pnl: Decimal | None = None
    fees: Decimal | None = None
    slippage: Decimal | None = None
    spread_cost: Decimal | None = None
    r_multiple: Decimal | None = None

    model_config = {"arbitrary_types_allowed": True}


class ReportOpenTrade(BaseModel):
    """Open / incomplete trade kept strictly separate from completed metrics."""

    trade_id: str
    symbol: str
    direction: str
    lifecycle_status: str
    analytics_class: str
    entry_timestamp: datetime | None = None
    entry_price: Decimal | None = None
    original_quantity: Decimal | None = None
    remaining_quantity: Decimal | None = None
    executed_quantity: Decimal | None = None
    initial_stop_loss: Decimal | None = None
    current_stop_loss: Decimal | None = None
    take_profit_levels: list[Decimal] = Field(default_factory=list)
    unrealized_note: str = "Open or incomplete — not included in completed-trade metrics."

    model_config = {"arbitrary_types_allowed": True}


# ─── Summary view (pass-through) ───


class ReportKeyMetric(BaseModel):
    key: str
    label: str
    value: Decimal | None = None
    availability: MetricAvailability = "available"
    unit: str = ""

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def from_metric(cls, key: str, label: str, metric: MetricValue, unit: str = "") -> "ReportKeyMetric":
        return cls(
            key=key,
            label=label,
            value=metric.value if metric.availability == "available" else None,
            availability=metric.availability,
            unit=unit,
        )

    @classmethod
    def decimal(cls, key: str, label: str, value: Decimal, unit: str = "") -> "ReportKeyMetric":
        return cls(key=key, label=label, value=value, availability="available", unit=unit)


class ReportSummary(BaseModel):
    """View over the existing PerformanceSummary — no new math."""

    completed_trade_count: int
    total_simulated_trades: int
    winning_trades: int
    losing_trades: int
    break_even_trades: int
    partially_closed_trades: int
    open_trades: int
    excluded_open_trades: int
    excluded_partial_trades: int

    win_rate: MetricValue
    profit_factor: MetricValue
    average_net_pnl_per_completed: MetricValue
    average_r_multiple: MetricValue

    gross_pnl: Decimal
    net_pnl: Decimal
    total_fees: Decimal
    total_slippage: Decimal
    total_spread_cost: Decimal
    total_execution_costs: Decimal

    initial_equity: Decimal | None = None
    ending_equity: MetricValue
    current_equity: MetricValue
    total_return_pct: MetricValue

    max_drawdown: Decimal
    max_drawdown_pct: MetricValue
    current_drawdown: Decimal
    recovery_timestamp: datetime | None = None
    peak_timestamp: datetime | None = None
    trough_timestamp: datetime | None = None

    key_metrics: list[ReportKeyMetric] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}


# ─── Equity / Drawdown views (pass-through) ───


class ReportEquitySection(BaseModel):
    completed: EquityCurve
    cashflow: EquityCurve

    model_config = {"arbitrary_types_allowed": True}


class ReportDrawdownSection(BaseModel):
    summary: DrawdownSummary
    points: list[DrawdownPoint] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}


# ─── Snapshot ───


class BacktestReportSnapshot(BaseModel):
    metadata: ReportMetadata
    summary: ReportSummary
    performance_summary: PerformanceSummary  # full underlying analytics summary
    equity: ReportEquitySection
    drawdown: ReportDrawdownSection
    groups: PerformanceGroups
    completed_trades: list[ReportTradeDetail] = Field(default_factory=list)
    completed_trade_total: int = 0
    completed_trades_truncated: bool = False
    open_trades: list[ReportOpenTrade] = Field(default_factory=list)
    open_trade_total: int = 0
    open_trades_truncated: bool = False
    limitations: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    disclaimer: str

    model_config = {"arbitrary_types_allowed": True}


# ─── Export artifact ───


class ExportArtifact(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
    kind: str

    model_config = {"arbitrary_types_allowed": True}
