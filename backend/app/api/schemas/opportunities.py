"""Pydantic schemas for Market Opportunities API (Phase 5.5)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.scanner.models import (
    MarketOpportunity,
    OpportunityStatus,
    ScanRunSummary,
    ScannerStatus,
)


class OpportunityListResponse(BaseModel):
    opportunities: list[MarketOpportunity]
    total: int
    actionable_total: int
    disclaimer: str = (
        "Analysis only — opportunities are not executed trades and do not guarantee profit."
    )


class OpportunityDetailResponse(BaseModel):
    opportunity: MarketOpportunity
    disclaimer: str = (
        "Planned levels are analytical. Vision does not generate Entry/SL/TP."
    )


class ScannerStatusResponse(BaseModel):
    status: ScannerStatus


class ScanHistoryResponse(BaseModel):
    scans: list[ScanRunSummary]


class ScanTriggerResponse(BaseModel):
    scan: ScanRunSummary
    message: str


class OpportunityFilters(BaseModel):
    exchange: ExchangeId | None = None
    market_type: MarketType | None = None
    timeframe: Timeframe | None = None
    direction: Literal["LONG", "SHORT"] | None = None
    status: OpportunityStatus | None = None
    search: str | None = None
    actionable_only: bool = False
    sort: Literal["confluence", "freshness", "entry_distance", "rank"] = "rank"
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
