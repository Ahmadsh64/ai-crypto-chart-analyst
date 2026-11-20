"""API schemas for historical replay (Phase 5.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.replay.analysis.models import HistoricalAnalysisSnapshot
from app.replay.config import REPLAY_TIMEFRAMES, ReplaySpeed, ReplayStatus
from app.replay.models import ReplaySessionInfo, ReplaySnapshot
from app.replay.analytics.config import AnalyticsConfig
from app.replay.analytics.models import (
    AnalyticsSnapshot,
    AnalyticsTradeRow,
    DrawdownSummary,
    EquityCurve,
    PerformanceGroups,
    PerformanceSummary,
)
from app.replay.costs.config import ExecutionCostConfig
from app.replay.costs.models import (
    CostSnapshot,
    LedgerEntry,
    SessionCostSummary,
    TradeCostSummary,
)
from app.replay.simulation.models import (
    SimulatedTrade,
    SimulationExecutionEvent,
    SimulationSnapshot,
)

ALLOWED_REPLAY_TFS = {tf.value for tf in REPLAY_TIMEFRAMES}


class CreateReplaySessionRequest(BaseModel):
    exchange: ExchangeId
    symbol: str = Field(..., min_length=3, max_length=32)
    market_type: MarketType
    start_time: datetime
    end_time: datetime
    timeframes: list[Timeframe] | None = None
    speed: ReplaySpeed = "10x"

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, v: str) -> str:
        cleaned = v.strip().upper().replace("-", "/")
        return cleaned

    @field_validator("timeframes")
    @classmethod
    def validate_timeframes(cls, v: list[Timeframe] | None) -> list[Timeframe] | None:
        if v is None:
            return None
        for tf in v:
            if tf.value not in ALLOWED_REPLAY_TFS:
                raise ValueError(
                    f"Unsupported replay timeframe {tf.value}; "
                    f"allowed: {sorted(ALLOWED_REPLAY_TFS)}"
                )
        # Preserve order uniqueness
        seen: set[Timeframe] = set()
        out: list[Timeframe] = []
        for tf in v:
            if tf not in seen:
                seen.add(tf)
                out.append(tf)
        if Timeframe.M5 not in out:
            raise ValueError("5m timeframe is required (replay clock base).")
        return out

    @model_validator(mode="after")
    def check_range(self) -> CreateReplaySessionRequest:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        # Exchange / market_type compatibility
        if self.exchange == ExchangeId.BINANCE and self.market_type not in {
            MarketType.SPOT,
            MarketType.USDT_M_FUTURES,
        }:
            raise ValueError("Binance supports spot and usdt_m_futures only.")
        if self.exchange == ExchangeId.BYBIT and self.market_type not in {
            MarketType.SPOT,
            MarketType.LINEAR_PERPETUAL,
        }:
            raise ValueError("Bybit supports spot and linear_perpetual only.")
        return self


class ReplaySpeedRequest(BaseModel):
    speed: ReplaySpeed


class ReplaySeekRequest(BaseModel):
    """Seek by event index XOR timestamp (Phase 5.2.7). Exactly one field required."""

    event_index: int | None = None
    timestamp: datetime | None = None

    @model_validator(mode="after")
    def exactly_one_target(self) -> ReplaySeekRequest:
        has_idx = self.event_index is not None
        has_ts = self.timestamp is not None
        if has_idx == has_ts:
            raise ValueError("Provide exactly one of event_index or timestamp")
        return self


class ReplaySessionResponse(BaseModel):
    session: ReplaySessionInfo
    snapshot: ReplaySnapshot


class ReplayControlResponse(BaseModel):
    session_id: str
    status: ReplayStatus
    speed: ReplaySpeed
    snapshot: ReplaySnapshot
    message: str | None = None


class ReplayDeleteResponse(BaseModel):
    session_id: str
    deleted: Literal[True] = True


class ReplayAnalysisToggleResponse(BaseModel):
    session_id: str
    analysis_enabled: bool
    snapshot: HistoricalAnalysisSnapshot | None = None
    message: str | None = None


class ReplayAnalysisCurrentResponse(BaseModel):
    session_id: str
    analysis_enabled: bool
    snapshot: HistoricalAnalysisSnapshot | None = None


# ─── Phase 5.2.2 Trade Simulation ───


class ReplaySimulationToggleResponse(BaseModel):
    session_id: str
    simulation_enabled: bool
    analysis_enabled: bool
    snapshot: SimulationSnapshot
    message: str | None = None


class ReplaySimulationCurrentResponse(BaseModel):
    session_id: str
    simulation_enabled: bool
    snapshot: SimulationSnapshot


class ReplaySimulationTradesResponse(BaseModel):
    session_id: str
    count: int
    offset: int
    limit: int
    total: int
    trades: list[SimulatedTrade]


class ReplaySimulationEventsResponse(BaseModel):
    session_id: str
    count: int
    offset: int
    limit: int
    total: int
    events: list[SimulationExecutionEvent]


# ─── Phase 5.2.3 Execution Costs ───


class ReplayCostToggleResponse(BaseModel):
    session_id: str
    costs_enabled: bool
    simulation_enabled: bool
    analysis_enabled: bool
    snapshot: CostSnapshot
    message: str | None = None


class ReplayCostCurrentResponse(BaseModel):
    session_id: str
    costs_enabled: bool
    snapshot: CostSnapshot


class ReplayCostConfigResponse(BaseModel):
    session_id: str
    costs_enabled: bool
    config: ExecutionCostConfig


class ReplayCostConfigUpdateRequest(BaseModel):
    """Partial user overrides for execution cost modeling."""

    maker_fee_rate: float | None = None
    taker_fee_rate: float | None = None
    fee_currency: str | None = None
    slippage_policy: str | None = None
    slippage_bps: float | None = None
    slippage_percentage: float | None = None
    spread_policy: str | None = None
    spread_bps: float | None = None
    spread_percentage: float | None = None
    maker_taker_fallback: str | None = None
    contract_multiplier: float | None = None


class ReplayCostSummaryResponse(BaseModel):
    session_id: str
    summary: SessionCostSummary


class ReplayCostTradesResponse(BaseModel):
    session_id: str
    count: int
    trades: list[TradeCostSummary]


class ReplayCostLedgerResponse(BaseModel):
    session_id: str
    count: int
    offset: int
    limit: int
    total: int
    entries: list[LedgerEntry]


# ─── Phase 5.2.4 Performance Analytics ───


class ReplayAnalyticsToggleResponse(BaseModel):
    session_id: str
    analytics_enabled: bool
    costs_enabled: bool
    simulation_enabled: bool
    analysis_enabled: bool
    snapshot: AnalyticsSnapshot | None = None
    message: str | None = None


class ReplayAnalyticsCurrentResponse(BaseModel):
    session_id: str
    analytics_enabled: bool
    snapshot: AnalyticsSnapshot


class ReplayAnalyticsConfigResponse(BaseModel):
    session_id: str
    analytics_enabled: bool
    config: AnalyticsConfig


class ReplayAnalyticsConfigUpdateRequest(BaseModel):
    initial_equity: float | None = None
    quote_currency: str | None = None
    include_closed_only_for_stats: bool | None = None
    include_partial_realized_in_cashflow: bool | None = None
    equity_curve_mode: str | None = None
    drawdown_mode: str | None = None
    time_group_period: str | None = None
    display_timezone: str | None = None
    clear_initial_equity: bool = False


class ReplayAnalyticsFilterRequest(BaseModel):
    exchange: str | None = None
    symbol: str | None = None
    market_type: str | None = None
    direction: str | None = None
    exit_type: str | None = None
    start_time: str | None = None
    end_time: str | None = None


class ReplayAnalyticsSummaryResponse(BaseModel):
    session_id: str
    summary: PerformanceSummary


class ReplayAnalyticsEquityResponse(BaseModel):
    session_id: str
    completed: EquityCurve
    cashflow: EquityCurve


class ReplayAnalyticsDrawdownResponse(BaseModel):
    session_id: str
    drawdown: DrawdownSummary


class ReplayAnalyticsGroupsResponse(BaseModel):
    session_id: str
    groups: PerformanceGroups


class ReplayAnalyticsTradesResponse(BaseModel):
    session_id: str
    count: int
    trades: list[AnalyticsTradeRow]


# ─── Phase 5.2.6 Backtesting Reporting ───


from app.replay.reporting.models import (  # noqa: E402  (grouped for clarity)
    BacktestReportSnapshot,
    ReportDrawdownSection,
    ReportEquitySection,
    ReportOpenTrade,
    ReportSummary,
    ReportTradeDetail,
)


class ReplayReportResponse(BaseModel):
    session_id: str
    analytics_enabled: bool
    report: BacktestReportSnapshot


class ReplayReportSummaryResponse(BaseModel):
    session_id: str
    report_id: str
    generated_at: datetime
    summary: ReportSummary


class ReplayReportTradesResponse(BaseModel):
    session_id: str
    report_id: str
    completed_trade_total: int
    completed_trades_truncated: bool
    open_trade_total: int
    open_trades_truncated: bool
    completed_trades: list[ReportTradeDetail]
    open_trades: list[ReportOpenTrade]


class ReplayReportEquityResponse(BaseModel):
    session_id: str
    report_id: str
    equity: ReportEquitySection


class ReplayReportDrawdownResponse(BaseModel):
    session_id: str
    report_id: str
    drawdown: ReportDrawdownSection
