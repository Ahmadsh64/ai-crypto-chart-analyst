"""Market Opportunities API (Phase 5.5)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.api.schemas.opportunities import (
    OpportunityDetailResponse,
    OpportunityListResponse,
    ScanHistoryResponse,
    ScanTriggerResponse,
    ScannerStatusResponse,
)
from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.scanner.models import MarketOpportunity, OpportunityStatus
from app.scanner.service import get_scanner
from app.scanner.store import get_opportunity_store

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


def _filter_sort(
    items: list[MarketOpportunity],
    *,
    exchange: ExchangeId | None,
    market_type: MarketType | None,
    timeframe: Timeframe | None,
    direction: str | None,
    status: OpportunityStatus | None,
    search: str | None,
    actionable_only: bool,
    sort: str,
) -> list[MarketOpportunity]:
    out = items
    if exchange is not None:
        out = [o for o in out if o.exchange == exchange]
    if market_type is not None:
        out = [o for o in out if o.market_type == market_type]
    if timeframe is not None:
        out = [o for o in out if o.timeframe == timeframe]
    if direction is not None:
        out = [o for o in out if o.direction and o.direction.value == direction]
    if status is not None:
        out = [o for o in out if o.status == status]
    if actionable_only:
        out = [o for o in out if o.actionable and o.status == OpportunityStatus.READY]
    if search:
        needle = search.strip().upper().replace("-", "/").replace(" ", "")
        compact = needle.replace("/", "")
        out = [
            o
            for o in out
            if needle in o.symbol.upper()
            or compact in o.symbol.upper().replace("/", "")
            or needle in o.base.upper()
        ]

    if sort == "confluence":
        out = sorted(out, key=lambda o: -(o.confluence_score or 0.0))
    elif sort == "freshness":
        out = sorted(
            out,
            key=lambda o: o.analysis_timestamp or datetime(1970, 1, 1),
            reverse=True,
        )
    elif sort == "entry_distance":
        out = sorted(
            out,
            key=lambda o: o.entry_distance_pct if o.entry_distance_pct is not None else 1e9,
        )
    else:
        out = sorted(out, key=lambda o: -o.rank_score)
    return out


@router.get("", response_model=OpportunityListResponse)
async def list_opportunities(
    exchange: ExchangeId | None = Query(default=None),
    market_type: MarketType | None = Query(default=None),
    timeframe: Timeframe | None = Query(default=None),
    direction: str | None = Query(default=None, pattern="^(LONG|SHORT)$"),
    status: OpportunityStatus | None = Query(default=None),
    search: str | None = Query(default=None),
    actionable_only: bool = Query(default=False),
    sort: str = Query(default="rank", pattern="^(confluence|freshness|entry_distance|rank)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> OpportunityListResponse:
    store = get_opportunity_store()
    filtered = _filter_sort(
        store.list_opportunities(),
        exchange=exchange,
        market_type=market_type,
        timeframe=timeframe,
        direction=direction,
        status=status,
        search=search,
        actionable_only=actionable_only,
        sort=sort,
    )
    page = filtered[offset : offset + limit]
    actionable_total = sum(
        1 for o in filtered if o.actionable and o.status == OpportunityStatus.READY
    )
    return OpportunityListResponse(
        opportunities=page,
        total=len(filtered),
        actionable_total=actionable_total,
    )


@router.get("/status", response_model=ScannerStatusResponse)
async def scanner_status() -> ScannerStatusResponse:
    return ScannerStatusResponse(status=get_opportunity_store().status())


@router.get("/history", response_model=ScanHistoryResponse)
async def scan_history() -> ScanHistoryResponse:
    return ScanHistoryResponse(scans=get_opportunity_store().history())


@router.post("/scan", response_model=ScanTriggerResponse)
async def trigger_scan() -> ScanTriggerResponse:
    scan = await get_scanner().run_scan(trigger="manual")
    msg = (
        "Scan skipped — already running"
        if scan.status == "skipped"
        else f"Scan {scan.status}"
    )
    return ScanTriggerResponse(scan=scan, message=msg)


@router.get("/{opportunity_id}", response_model=OpportunityDetailResponse)
async def get_opportunity(opportunity_id: str) -> OpportunityDetailResponse:
    opp = get_opportunity_store().get(opportunity_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return OpportunityDetailResponse(opportunity=opp)
