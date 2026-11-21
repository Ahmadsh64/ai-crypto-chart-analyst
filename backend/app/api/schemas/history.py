"""Read-only analysis history schemas (Phase 6.0.3.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AnalysisHistoryListItem(BaseModel):
    analysis_run_id: str
    snapshot_id: str
    analysis_session_id: str | None = None
    exchange: str
    market_type: str
    symbol: str
    timeframe: str | None = None
    analysis_timestamp: datetime
    decision: str
    consistency_status: str
    decision_analysis_timestamp: datetime | None = None
    trade_plan_analysis_timestamp: datetime | None = None
    entry_reference_price: str | None = None
    stop_loss_price: str | None = None
    take_profit_prices: list[str] = Field(default_factory=list)
    primary_rr: str | None = None
    data_freshness: str | None = None
    created_at: datetime


class AnalysisHistoryListResponse(BaseModel):
    items: list[AnalysisHistoryListItem]
    total: int
    limit: int
    offset: int


class AnalysisSessionSummary(BaseModel):
    id: str
    exchange: str
    market_type: str
    symbol: str
    primary_timeframe: str | None = None
    status: str
    source: str
    created_at: datetime
    updated_at: datetime


class AnalysisHistoryDetailResponse(BaseModel):
    """Immutable stored Analyze bundle — never recomputed."""

    analysis_run_id: str
    snapshot_id: str
    consistency_status: str
    snapshot_kind: str
    exchange: str
    market_type: str
    symbol: str
    timeframe: str | None = None
    analysis_timestamp: datetime
    decision_analysis_timestamp: datetime | None = None
    trade_plan_analysis_timestamp: datetime | None = None
    decision: str
    decision_id: str | None = None
    plan_id: str | None = None
    configuration_versions: dict[str, Any] = Field(default_factory=dict)
    snapshot_schema_version: str
    data_freshness: str | None = None
    # Decision-preferred typed extracts (planned analytical levels — not fills)
    entry_reference_price: str | None = None
    entry_low: str | None = None
    entry_high: str | None = None
    stop_loss_price: str | None = None
    take_profit_prices: list[str] = Field(default_factory=list)
    primary_rr: str | None = None
    confluence_bullish: str | None = None
    confluence_bearish: str | None = None
    content_hash: str
    created_at: datetime
    levels_note: str = (
        "Stored planned Entry/SL/TP are analytical levels from Analyze time — "
        "not exchange fills."
    )
    session: AnalysisSessionSummary | None = None
    snapshot_payload: dict[str, Any] = Field(default_factory=dict)
    decision_extract: dict[str, Any] | None = None
    trade_plan_extract: dict[str, Any] | None = None
