"""Opportunity and scan-run models (Phase 5.5). Analysis-only — not fills."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.exchanges.types import ExchangeId, MarketType, Timeframe


class OpportunityStatus(str, Enum):
    READY = "READY"
    APPROACHING_ENTRY = "APPROACHING_ENTRY"
    WAITING = "WAITING"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class OpportunityDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class OpportunityLevel(BaseModel):
    label: str
    price: float | None = None
    available: bool = False


class MarketOpportunity(BaseModel):
    opportunity_id: str
    exchange: ExchangeId
    market_type: MarketType
    symbol: str
    base: str
    timeframe: Timeframe
    status: OpportunityStatus
    decision: Literal["LONG", "SHORT", "WAIT", "NO TRADE"] | None = None
    decision_reason: str = ""
    # Planned analytical direction (from Trade Plan / Decision). Not a fill.
    direction: OpportunityDirection | None = None
    # True when the selected market type can execute this planned direction
    # (e.g. Spot SHORT → False). Independent of actionable / READY.
    market_executable: bool = True
    executability_note: str = ""
    current_price: float | None = None
    price_updated_at: datetime | None = None
    price_source: str = "exchange"
    entry_reference: float | None = None
    entry_low: float | None = None
    entry_high: float | None = None
    stop_loss: float | None = None
    take_profits: list[OpportunityLevel] = Field(default_factory=list)
    primary_rr: float | None = None
    confluence_bullish: float | None = None
    confluence_bearish: float | None = None
    confluence_score: float | None = None
    supporting_evidence: list[str] = Field(default_factory=list)
    blocking_conditions: list[str] = Field(default_factory=list)
    entry_distance_pct: float | None = None
    quote_volume_24h: float | None = None
    analysis_timestamp: datetime | None = None
    decision_id: str | None = None
    trade_plan_id: str | None = None
    lifecycle: str | None = None
    rank_score: float = 0.0
    rank_explanation: str = ""
    actionable: bool = False
    planned_not_fills_note: str = (
        "Planned analytical levels from the deterministic engine — not executed fills."
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScanRunSummary(BaseModel):
    scan_id: str
    started_at: datetime
    finished_at: datetime | None = None
    status: Literal[
        "running",
        "completed",
        "completed_partial",
        "failed",
        "skipped",
    ] = "running"
    # Universe staging
    pairs_discovered: int = 0
    pairs_eligible: int = 0
    pairs_selected: int = 0
    pairs_targeted: int = 0  # alias of selected (jobs planned)
    pairs_scanned: int = 0  # pairs with ALL execution TFs completed
    pairs_partial: int = 0  # pairs with some but not all TFs completed
    pairs_failed: int = 0  # pairs with zero TF completions
    # Timeframe matrix
    timeframe_analyses_attempted: int = 0
    timeframe_analyses_completed: int = 0
    timeframe_analyses_failed: int = 0
    opportunities_found: int = 0
    ready_count: int = 0
    long_count: int = 0
    short_count: int = 0
    duration_seconds: float | None = None
    ranking_method: str = ""
    excluded_pairs: list[dict[str, Any]] = Field(default_factory=list)
    per_market: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    exchanges: list[str] = Field(default_factory=list)


class ScannerStatus(BaseModel):
    state: Literal["idle", "scanning", "error", "disabled"] = "idle"
    last_scan: ScanRunSummary | None = None
    pairs_monitored: int = 0
    pairs_scanned_total: int = 0
    qualified_opportunities: int = 0
    long_opportunities: int = 0
    short_opportunities: int = 0
    ready_opportunities: int = 0
    waiting_opportunities: int = 0
    approaching_opportunities: int = 0
    invalidated_opportunities: int = 0
    expired_opportunities: int = 0
    data_unavailable_opportunities: int = 0
    last_successful_scan_at: datetime | None = None
    next_scan_at: datetime | None = None
    scan_interval_seconds: float = 300.0
    message: str = ""
