"""Historical replay REST endpoints (Phases 5.1–5.2.3)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.api.routes.market import _http_for_exchange_error, _normalize_symbol
from app.api.schemas.replay import (
    CreateReplaySessionRequest,
    ReplayAnalysisCurrentResponse,
    ReplayAnalysisToggleResponse,
    ReplayAnalyticsConfigResponse,
    ReplayAnalyticsConfigUpdateRequest,
    ReplayAnalyticsCurrentResponse,
    ReplayAnalyticsDrawdownResponse,
    ReplayAnalyticsEquityResponse,
    ReplayAnalyticsFilterRequest,
    ReplayAnalyticsGroupsResponse,
    ReplayAnalyticsSummaryResponse,
    ReplayAnalyticsToggleResponse,
    ReplayAnalyticsTradesResponse,
    ReplayControlResponse,
    ReplayReportDrawdownResponse,
    ReplayReportEquityResponse,
    ReplayReportResponse,
    ReplayReportSummaryResponse,
    ReplayReportTradesResponse,
    ReplayCostConfigResponse,
    ReplayCostConfigUpdateRequest,
    ReplayCostCurrentResponse,
    ReplayCostLedgerResponse,
    ReplayCostSummaryResponse,
    ReplayCostToggleResponse,
    ReplayCostTradesResponse,
    ReplayDeleteResponse,
    ReplaySeekRequest,
    ReplaySessionResponse,
    ReplaySimulationCurrentResponse,
    ReplaySimulationEventsResponse,
    ReplaySimulationToggleResponse,
    ReplaySimulationTradesResponse,
    ReplaySpeedRequest,
)
from app.replay.analytics.config import AnalyticsConfig
from app.replay.analytics.trade_filter import AnalyticsFilter
from app.replay.costs.config import ExecutionCostConfig
from app.replay.costs.models import TradeCostSummary
from app.replay.simulation.models import SimulatedTrade
from app.exchanges.exceptions import ExchangeError
from app.replay.analysis.models import (
    HistoricalAnalysisHistoryResponse,
    HistoricalAnalysisSnapshot,
)
from app.replay.config import REPLAY_TIMEFRAMES
from app.replay.manager import get_replay_manager
from app.replay.reporting import (
    EXPORT_KINDS,
    ExportKind,
    ReportError,
    build_export_filename,
    build_report,
    render_csv,
    render_pdf,
)
from app.replay.timeline import ensure_utc, event_index_at_or_before

router = APIRouter(prefix="/replay", tags=["replay"])


def _session_response(session) -> ReplaySessionResponse:
    return ReplaySessionResponse(session=session.info(), snapshot=session.current_snapshot())


def _control(session, message: str | None = None) -> ReplayControlResponse:
    snap = session.current_snapshot()
    return ReplayControlResponse(
        session_id=session.session_id,
        status=session.status,
        speed=session.speed,
        snapshot=snap,
        message=message,
    )


@router.post("/sessions", response_model=ReplaySessionResponse)
async def create_replay_session(body: CreateReplaySessionRequest) -> ReplaySessionResponse:
    """Create a replay session and load historical candles."""
    symbol = _normalize_symbol(body.symbol)
    tfs = tuple(body.timeframes) if body.timeframes else REPLAY_TIMEFRAMES
    manager = get_replay_manager()
    try:
        session = await manager.create_session(
            exchange=body.exchange,
            symbol=symbol,
            market_type=body.market_type,
            start_time=body.start_time,
            end_time=body.end_time,
            timeframes=tfs,
            speed=body.speed,
            load=True,
        )
    except ExchangeError as exc:
        raise _http_for_exchange_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _session_response(session)


@router.get("/sessions/{session_id}", response_model=ReplaySessionResponse)
async def get_replay_session(session_id: str) -> ReplaySessionResponse:
    session = get_replay_manager().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Replay session not found")
    return _session_response(session)


@router.post("/sessions/{session_id}/start", response_model=ReplayControlResponse)
async def start_replay(session_id: str) -> ReplayControlResponse:
    session = _require(session_id)
    try:
        await session.start()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _control(session, "started")


@router.post("/sessions/{session_id}/pause", response_model=ReplayControlResponse)
async def pause_replay(session_id: str) -> ReplayControlResponse:
    session = _require(session_id)
    await session.pause()
    return _control(session, "paused")


@router.post("/sessions/{session_id}/resume", response_model=ReplayControlResponse)
async def resume_replay(session_id: str) -> ReplayControlResponse:
    session = _require(session_id)
    await session.resume()
    return _control(session, "resumed")


@router.post("/sessions/{session_id}/stop", response_model=ReplayControlResponse)
async def stop_replay(session_id: str) -> ReplayControlResponse:
    session = _require(session_id)
    await session.stop()
    return _control(session, "stopped")


@router.post("/sessions/{session_id}/step", response_model=ReplayControlResponse)
async def step_replay(session_id: str) -> ReplayControlResponse:
    session = _require(session_id)
    try:
        await session.step()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _control(session, "step")


@router.post("/sessions/{session_id}/reset", response_model=ReplayControlResponse)
async def reset_replay(session_id: str) -> ReplayControlResponse:
    session = _require(session_id)
    await session.reset()
    return _control(session, "reset")


@router.post("/sessions/{session_id}/speed", response_model=ReplayControlResponse)
async def set_replay_speed(
    session_id: str,
    body: ReplaySpeedRequest,
) -> ReplayControlResponse:
    session = _require(session_id)
    await session.set_speed(body.speed)
    return _control(session, f"speed={body.speed}")


@router.post("/sessions/{session_id}/seek", response_model=ReplayControlResponse)
async def seek_replay(
    session_id: str,
    body: ReplaySeekRequest,
) -> ReplayControlResponse:
    """Jump replay clock to an event index or timestamp (Phase 5.2.7).

    Reuses ReplaySession.seek rebuild (analysis → sim → costs → analytics).
    Timestamp maps to the latest event with event_time <= timestamp (UTC).
    """
    session = _require(session_id)
    if not session.event_times:
        raise HTTPException(status_code=400, detail="No events loaded.")

    if body.event_index is not None:
        target = int(body.event_index)
    else:
        assert body.timestamp is not None
        try:
            target = event_index_at_or_before(session.event_times, body.timestamp)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        await session.seek(target)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _control(session, f"seek event_index={session.event_index}")


@router.delete("/sessions/{session_id}", response_model=ReplayDeleteResponse)
async def delete_replay_session(session_id: str) -> ReplayDeleteResponse:
    ok = await get_replay_manager().delete(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Replay session not found")
    return ReplayDeleteResponse(session_id=session_id)


@router.post(
    "/sessions/{session_id}/analysis/enable",
    response_model=ReplayAnalysisToggleResponse,
)
async def enable_replay_analysis(session_id: str) -> ReplayAnalysisToggleResponse:
    """Enable historical analysis pipeline for this session (Phase 5.2.1)."""
    session = _require(session_id)
    snap = await session.enable_analysis()
    return ReplayAnalysisToggleResponse(
        session_id=session.session_id,
        analysis_enabled=True,
        snapshot=snap,
        message="historical analysis enabled",
    )


@router.post(
    "/sessions/{session_id}/analysis/disable",
    response_model=ReplayAnalysisToggleResponse,
)
async def disable_replay_analysis(session_id: str) -> ReplayAnalysisToggleResponse:
    session = _require(session_id)
    await session.disable_analysis()
    return ReplayAnalysisToggleResponse(
        session_id=session.session_id,
        analysis_enabled=False,
        snapshot=session.get_analysis(),
        message="historical analysis disabled",
    )


@router.get(
    "/sessions/{session_id}/analysis",
    response_model=ReplayAnalysisCurrentResponse,
)
async def get_current_replay_analysis(session_id: str) -> ReplayAnalysisCurrentResponse:
    session = _require(session_id)
    return ReplayAnalysisCurrentResponse(
        session_id=session.session_id,
        analysis_enabled=session.analysis_enabled,
        snapshot=session.get_analysis(),
    )


@router.get(
    "/sessions/{session_id}/analysis/history",
    response_model=HistoricalAnalysisHistoryResponse,
)
async def get_replay_analysis_history(
    session_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
) -> HistoricalAnalysisHistoryResponse:
    session = _require(session_id)
    items, total = session.list_analysis_history(
        offset=offset,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
    )
    return HistoricalAnalysisHistoryResponse(
        session_id=session.session_id,
        count=len(items),
        offset=offset,
        limit=limit,
        total=total,
        snapshots=items,
    )


@router.get(
    "/sessions/{session_id}/analysis/at/{timestamp}",
    response_model=HistoricalAnalysisSnapshot,
)
async def get_replay_analysis_at_timestamp(
    session_id: str,
    timestamp: datetime,
) -> HistoricalAnalysisSnapshot:
    session = _require(session_id)
    snap = session.get_analysis_at(ensure_utc(timestamp))
    if snap is None:
        raise HTTPException(
            status_code=404,
            detail="No historical analysis snapshot for that timestamp",
        )
    return snap


@router.post(
    "/sessions/{session_id}/simulation/enable",
    response_model=ReplaySimulationToggleResponse,
)
async def enable_replay_simulation(session_id: str) -> ReplaySimulationToggleResponse:
    """Enable historical trade simulation (Phase 5.2.2). Also enables analysis."""
    session = _require(session_id)
    snap = await session.enable_simulation()
    return ReplaySimulationToggleResponse(
        session_id=session.session_id,
        simulation_enabled=True,
        analysis_enabled=session.analysis_enabled,
        snapshot=snap,
        message="historical trade simulation enabled",
    )


@router.post(
    "/sessions/{session_id}/simulation/disable",
    response_model=ReplaySimulationToggleResponse,
)
async def disable_replay_simulation(session_id: str) -> ReplaySimulationToggleResponse:
    session = _require(session_id)
    snap = await session.disable_simulation()
    return ReplaySimulationToggleResponse(
        session_id=session.session_id,
        simulation_enabled=False,
        analysis_enabled=session.analysis_enabled,
        snapshot=snap,
        message="historical trade simulation disabled",
    )


@router.get(
    "/sessions/{session_id}/simulation",
    response_model=ReplaySimulationCurrentResponse,
)
async def get_replay_simulation(session_id: str) -> ReplaySimulationCurrentResponse:
    session = _require(session_id)
    clock = (
        session.event_times[session.event_index] if session.event_times else None
    )
    return ReplaySimulationCurrentResponse(
        session_id=session.session_id,
        simulation_enabled=session.simulator.enabled,
        snapshot=session.simulator.snapshot(clock),
    )


@router.get(
    "/sessions/{session_id}/simulation/trades",
    response_model=ReplaySimulationTradesResponse,
)
async def list_replay_simulation_trades(
    session_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    status: str | None = Query(default=None),
) -> ReplaySimulationTradesResponse:
    session = _require(session_id)
    items, total = session.simulator.list_trades(
        status=status, offset=offset, limit=limit
    )
    return ReplaySimulationTradesResponse(
        session_id=session.session_id,
        count=len(items),
        offset=offset,
        limit=limit,
        total=total,
        trades=items,
    )


@router.get(
    "/sessions/{session_id}/simulation/trades/{trade_id}",
    response_model=SimulatedTrade,
)
async def get_replay_simulation_trade(
    session_id: str,
    trade_id: str,
) -> SimulatedTrade:
    session = _require(session_id)
    trade = session.simulator.get_trade(trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Simulated trade not found")
    return trade


@router.get(
    "/sessions/{session_id}/simulation/events",
    response_model=ReplaySimulationEventsResponse,
)
async def list_replay_simulation_events(
    session_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> ReplaySimulationEventsResponse:
    session = _require(session_id)
    items, total = session.simulator.list_events(offset=offset, limit=limit)
    return ReplaySimulationEventsResponse(
        session_id=session.session_id,
        count=len(items),
        offset=offset,
        limit=limit,
        total=total,
        events=items,
    )


@router.post(
    "/sessions/{session_id}/simulation/reset",
    response_model=ReplaySimulationToggleResponse,
)
async def reset_replay_simulation(session_id: str) -> ReplaySimulationToggleResponse:
    session = _require(session_id)
    snap = await session.reset_simulation()
    return ReplaySimulationToggleResponse(
        session_id=session.session_id,
        simulation_enabled=session.simulator.enabled,
        analysis_enabled=session.analysis_enabled,
        snapshot=snap,
        message="historical trade simulation reset",
    )


@router.post(
    "/sessions/{session_id}/costs/enable",
    response_model=ReplayCostToggleResponse,
)
async def enable_replay_costs(session_id: str) -> ReplayCostToggleResponse:
    """Enable execution cost modeling (Phase 5.2.3). Also enables simulation."""
    session = _require(session_id)
    snap = await session.enable_costs()
    return ReplayCostToggleResponse(
        session_id=session.session_id,
        costs_enabled=True,
        simulation_enabled=session.simulator.enabled,
        analysis_enabled=session.analysis_enabled,
        snapshot=snap,
        message="execution cost modeling enabled",
    )


@router.post(
    "/sessions/{session_id}/costs/disable",
    response_model=ReplayCostToggleResponse,
)
async def disable_replay_costs(session_id: str) -> ReplayCostToggleResponse:
    session = _require(session_id)
    snap = await session.disable_costs()
    return ReplayCostToggleResponse(
        session_id=session.session_id,
        costs_enabled=False,
        simulation_enabled=session.simulator.enabled,
        analysis_enabled=session.analysis_enabled,
        snapshot=snap,
        message="execution cost modeling disabled",
    )


@router.get(
    "/sessions/{session_id}/costs",
    response_model=ReplayCostCurrentResponse,
)
async def get_replay_costs(session_id: str) -> ReplayCostCurrentResponse:
    session = _require(session_id)
    clock = session.event_times[session.event_index] if session.event_times else None
    return ReplayCostCurrentResponse(
        session_id=session.session_id,
        costs_enabled=session.cost_engine.enabled,
        snapshot=session.cost_engine.snapshot(
            list(session.simulator.trades.values()),
            replay_timestamp=clock,
        ),
    )


@router.get(
    "/sessions/{session_id}/costs/config",
    response_model=ReplayCostConfigResponse,
)
async def get_replay_cost_config(session_id: str) -> ReplayCostConfigResponse:
    session = _require(session_id)
    return ReplayCostConfigResponse(
        session_id=session.session_id,
        costs_enabled=session.cost_engine.enabled,
        config=session.cost_config,
    )


@router.put(
    "/sessions/{session_id}/costs/config",
    response_model=ReplayCostToggleResponse,
)
async def update_replay_cost_config(
    session_id: str,
    body: ReplayCostConfigUpdateRequest,
) -> ReplayCostToggleResponse:
    """Update cost config and rebuild the ledger. Simulation fills are unchanged."""
    session = _require(session_id)
    current = session.cost_config.model_copy(deep=True)
    data = body.model_dump(exclude_unset=True)
    try:
        for key, value in data.items():
            if value is None:
                continue
            if key in {
                "maker_fee_rate",
                "taker_fee_rate",
                "slippage_bps",
                "slippage_percentage",
                "spread_bps",
                "spread_percentage",
                "contract_multiplier",
            }:
                setattr(current, key, Decimal(str(value)))
            else:
                setattr(current, key, value)
        if "maker_fee_rate" in data or "taker_fee_rate" in data:
            current.fee_source = "user"
            current.fee_schedule_version = "user-v1"
        current = ExecutionCostConfig.model_validate(current.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    snap = await session.update_cost_config(current)
    return ReplayCostToggleResponse(
        session_id=session.session_id,
        costs_enabled=session.cost_engine.enabled,
        simulation_enabled=session.simulator.enabled,
        analysis_enabled=session.analysis_enabled,
        snapshot=snap,
        message="cost configuration updated; ledger rebuilt",
    )


@router.get(
    "/sessions/{session_id}/costs/summary",
    response_model=ReplayCostSummaryResponse,
)
async def get_replay_cost_summary(session_id: str) -> ReplayCostSummaryResponse:
    session = _require(session_id)
    clock = session.event_times[session.event_index] if session.event_times else None
    return ReplayCostSummaryResponse(
        session_id=session.session_id,
        summary=session.cost_engine.session_summary(
            list(session.simulator.trades.values()),
            replay_timestamp=clock,
        ),
    )


@router.get(
    "/sessions/{session_id}/costs/trades",
    response_model=ReplayCostTradesResponse,
)
async def list_replay_cost_trades(session_id: str) -> ReplayCostTradesResponse:
    session = _require(session_id)
    trades: list[TradeCostSummary] = []
    for t in session.simulator.trades.values():
        if session.cost_engine.ledger.for_trade(t.trade_id):
            trades.append(session.cost_engine.trade_summary(t))
    return ReplayCostTradesResponse(
        session_id=session.session_id,
        count=len(trades),
        trades=trades,
    )


@router.get(
    "/sessions/{session_id}/costs/trades/{trade_id}",
    response_model=TradeCostSummary,
)
async def get_replay_cost_trade(session_id: str, trade_id: str) -> TradeCostSummary:
    session = _require(session_id)
    trade = session.simulator.get_trade(trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Simulated trade not found")
    return session.cost_engine.trade_summary(trade)


@router.get(
    "/sessions/{session_id}/costs/ledger",
    response_model=ReplayCostLedgerResponse,
)
async def list_replay_cost_ledger(
    session_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    trade_id: str | None = Query(default=None),
) -> ReplayCostLedgerResponse:
    session = _require(session_id)
    items, total = session.cost_engine.ledger.entries(
        offset=offset, limit=limit, trade_id=trade_id
    )
    return ReplayCostLedgerResponse(
        session_id=session.session_id,
        count=len(items),
        offset=offset,
        limit=limit,
        total=total,
        entries=items,
    )


@router.post(
    "/sessions/{session_id}/costs/reset",
    response_model=ReplayCostToggleResponse,
)
async def reset_replay_costs(session_id: str) -> ReplayCostToggleResponse:
    session = _require(session_id)
    snap = await session.reset_costs()
    return ReplayCostToggleResponse(
        session_id=session.session_id,
        costs_enabled=session.cost_engine.enabled,
        simulation_enabled=session.simulator.enabled,
        analysis_enabled=session.analysis_enabled,
        snapshot=snap,
        message="execution cost ledger reset",
    )


# ─── Phase 5.2.4 Performance Analytics ───


@router.post(
    "/sessions/{session_id}/analytics/enable",
    response_model=ReplayAnalyticsToggleResponse,
)
async def enable_replay_analytics(session_id: str) -> ReplayAnalyticsToggleResponse:
    """Enable performance analytics (also enables costs + simulation)."""
    session = _require(session_id)
    snap = await session.enable_analytics()
    return ReplayAnalyticsToggleResponse(
        session_id=session.session_id,
        analytics_enabled=True,
        costs_enabled=session.cost_engine.enabled,
        simulation_enabled=session.simulator.enabled,
        analysis_enabled=session.analysis_enabled,
        snapshot=snap,
        message="performance analytics enabled",
    )


@router.post(
    "/sessions/{session_id}/analytics/disable",
    response_model=ReplayAnalyticsToggleResponse,
)
async def disable_replay_analytics(session_id: str) -> ReplayAnalyticsToggleResponse:
    session = _require(session_id)
    snap = await session.disable_analytics()
    return ReplayAnalyticsToggleResponse(
        session_id=session.session_id,
        analytics_enabled=False,
        costs_enabled=session.cost_engine.enabled,
        simulation_enabled=session.simulator.enabled,
        analysis_enabled=session.analysis_enabled,
        snapshot=snap,
        message="performance analytics disabled",
    )


@router.get(
    "/sessions/{session_id}/analytics",
    response_model=ReplayAnalyticsCurrentResponse,
)
async def get_replay_analytics(session_id: str) -> ReplayAnalyticsCurrentResponse:
    session = _require(session_id)
    clock = session.event_times[session.event_index] if session.event_times else None
    snap = session.analytics_engine.snapshot(
        list(session.simulator.trades.values()),
        session.cost_engine,
        replay_timestamp=clock,
        event_index=session.event_index,
        filt=session.analytics_filter,
    )
    return ReplayAnalyticsCurrentResponse(
        session_id=session.session_id,
        analytics_enabled=session.analytics_engine.enabled,
        snapshot=snap,
    )


@router.get(
    "/sessions/{session_id}/analytics/config",
    response_model=ReplayAnalyticsConfigResponse,
)
async def get_replay_analytics_config(session_id: str) -> ReplayAnalyticsConfigResponse:
    session = _require(session_id)
    return ReplayAnalyticsConfigResponse(
        session_id=session.session_id,
        analytics_enabled=session.analytics_engine.enabled,
        config=session.analytics_config,
    )


@router.put(
    "/sessions/{session_id}/analytics/config",
    response_model=ReplayAnalyticsToggleResponse,
)
async def update_replay_analytics_config(
    session_id: str,
    body: ReplayAnalyticsConfigUpdateRequest,
) -> ReplayAnalyticsToggleResponse:
    session = _require(session_id)
    current = session.analytics_config.model_copy(deep=True)
    data = body.model_dump(exclude_unset=True)
    clear = data.pop("clear_initial_equity", False)
    try:
        if clear:
            current.initial_equity = None
        for key, value in data.items():
            if value is None and key != "initial_equity":
                continue
            if key == "initial_equity":
                if value is None:
                    current.initial_equity = None
                else:
                    current.initial_equity = Decimal(str(value))
            else:
                setattr(current, key, value)
        current = AnalyticsConfig.model_validate(current.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    snap = await session.update_analytics_config(current)
    return ReplayAnalyticsToggleResponse(
        session_id=session.session_id,
        analytics_enabled=session.analytics_engine.enabled,
        costs_enabled=session.cost_engine.enabled,
        simulation_enabled=session.simulator.enabled,
        analysis_enabled=session.analysis_enabled,
        snapshot=snap,
        message="analytics configuration updated",
    )


@router.put(
    "/sessions/{session_id}/analytics/filter",
    response_model=ReplayAnalyticsToggleResponse,
)
async def update_replay_analytics_filter(
    session_id: str,
    body: ReplayAnalyticsFilterRequest,
) -> ReplayAnalyticsToggleResponse:
    session = _require(session_id)
    filt = AnalyticsFilter(
        exchange=body.exchange,
        symbol=body.symbol,
        market_type=body.market_type,
        direction=body.direction,
        exit_type=body.exit_type,
        start_time_iso=body.start_time,
        end_time_iso=body.end_time,
    )
    snap = await session.set_analytics_filter(filt)
    return ReplayAnalyticsToggleResponse(
        session_id=session.session_id,
        analytics_enabled=session.analytics_engine.enabled,
        costs_enabled=session.cost_engine.enabled,
        simulation_enabled=session.simulator.enabled,
        analysis_enabled=session.analysis_enabled,
        snapshot=snap,
        message="analytics filter updated",
    )


@router.get(
    "/sessions/{session_id}/analytics/summary",
    response_model=ReplayAnalyticsSummaryResponse,
)
async def get_replay_analytics_summary(session_id: str) -> ReplayAnalyticsSummaryResponse:
    session = _require(session_id)
    clock = session.event_times[session.event_index] if session.event_times else None
    snap = session.analytics_engine.snapshot(
        list(session.simulator.trades.values()),
        session.cost_engine,
        replay_timestamp=clock,
        event_index=session.event_index,
        filt=session.analytics_filter,
    )
    return ReplayAnalyticsSummaryResponse(
        session_id=session.session_id, summary=snap.summary
    )


@router.get(
    "/sessions/{session_id}/analytics/equity",
    response_model=ReplayAnalyticsEquityResponse,
)
async def get_replay_analytics_equity(session_id: str) -> ReplayAnalyticsEquityResponse:
    session = _require(session_id)
    clock = session.event_times[session.event_index] if session.event_times else None
    snap = session.analytics_engine.snapshot(
        list(session.simulator.trades.values()),
        session.cost_engine,
        replay_timestamp=clock,
        event_index=session.event_index,
        filt=session.analytics_filter,
    )
    return ReplayAnalyticsEquityResponse(
        session_id=session.session_id,
        completed=snap.equity_completed,
        cashflow=snap.equity_cashflow,
    )


@router.get(
    "/sessions/{session_id}/analytics/drawdown",
    response_model=ReplayAnalyticsDrawdownResponse,
)
async def get_replay_analytics_drawdown(
    session_id: str,
) -> ReplayAnalyticsDrawdownResponse:
    session = _require(session_id)
    clock = session.event_times[session.event_index] if session.event_times else None
    snap = session.analytics_engine.snapshot(
        list(session.simulator.trades.values()),
        session.cost_engine,
        replay_timestamp=clock,
        event_index=session.event_index,
        filt=session.analytics_filter,
    )
    return ReplayAnalyticsDrawdownResponse(
        session_id=session.session_id, drawdown=snap.drawdown
    )


@router.get(
    "/sessions/{session_id}/analytics/groups",
    response_model=ReplayAnalyticsGroupsResponse,
)
async def get_replay_analytics_groups(session_id: str) -> ReplayAnalyticsGroupsResponse:
    session = _require(session_id)
    clock = session.event_times[session.event_index] if session.event_times else None
    snap = session.analytics_engine.snapshot(
        list(session.simulator.trades.values()),
        session.cost_engine,
        replay_timestamp=clock,
        event_index=session.event_index,
        filt=session.analytics_filter,
    )
    return ReplayAnalyticsGroupsResponse(
        session_id=session.session_id, groups=snap.groups
    )


@router.get(
    "/sessions/{session_id}/analytics/trades",
    response_model=ReplayAnalyticsTradesResponse,
)
async def get_replay_analytics_trades(session_id: str) -> ReplayAnalyticsTradesResponse:
    session = _require(session_id)
    clock = session.event_times[session.event_index] if session.event_times else None
    snap = session.analytics_engine.snapshot(
        list(session.simulator.trades.values()),
        session.cost_engine,
        replay_timestamp=clock,
        event_index=session.event_index,
        filt=session.analytics_filter,
    )
    return ReplayAnalyticsTradesResponse(
        session_id=session.session_id,
        count=len(snap.completed_trades),
        trades=snap.completed_trades,
    )


# ─── Phase 5.2.6 Backtesting Reporting & Export ───


def _build_report_or_http(session):
    try:
        return build_report(session)
    except ReportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _build_export_report_or_http(session):
    try:
        return build_report(session, for_export=True)
    except ReportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/sessions/{session_id}/report",
    response_model=ReplayReportResponse,
)
async def get_replay_report(session_id: str) -> ReplayReportResponse:
    """Full backtest report snapshot at the current replay clock."""
    session = _require(session_id)
    report = _build_report_or_http(session)
    return ReplayReportResponse(
        session_id=session.session_id,
        analytics_enabled=session.analytics_engine.enabled,
        report=report,
    )


@router.get(
    "/sessions/{session_id}/report/summary",
    response_model=ReplayReportSummaryResponse,
)
async def get_replay_report_summary(session_id: str) -> ReplayReportSummaryResponse:
    session = _require(session_id)
    report = _build_report_or_http(session)
    return ReplayReportSummaryResponse(
        session_id=session.session_id,
        report_id=report.metadata.report_id,
        generated_at=report.metadata.generated_at,
        summary=report.summary,
    )


@router.get(
    "/sessions/{session_id}/report/trades",
    response_model=ReplayReportTradesResponse,
)
async def get_replay_report_trades(session_id: str) -> ReplayReportTradesResponse:
    session = _require(session_id)
    report = _build_report_or_http(session)
    return ReplayReportTradesResponse(
        session_id=session.session_id,
        report_id=report.metadata.report_id,
        completed_trade_total=report.completed_trade_total,
        completed_trades_truncated=report.completed_trades_truncated,
        open_trade_total=report.open_trade_total,
        open_trades_truncated=report.open_trades_truncated,
        completed_trades=report.completed_trades,
        open_trades=report.open_trades,
    )


@router.get(
    "/sessions/{session_id}/report/equity",
    response_model=ReplayReportEquityResponse,
)
async def get_replay_report_equity(session_id: str) -> ReplayReportEquityResponse:
    session = _require(session_id)
    report = _build_report_or_http(session)
    return ReplayReportEquityResponse(
        session_id=session.session_id,
        report_id=report.metadata.report_id,
        equity=report.equity,
    )


@router.get(
    "/sessions/{session_id}/report/drawdown",
    response_model=ReplayReportDrawdownResponse,
)
async def get_replay_report_drawdown(session_id: str) -> ReplayReportDrawdownResponse:
    session = _require(session_id)
    report = _build_report_or_http(session)
    return ReplayReportDrawdownResponse(
        session_id=session.session_id,
        report_id=report.metadata.report_id,
        drawdown=report.drawdown,
    )


@router.get("/sessions/{session_id}/report/export/csv")
async def export_replay_report_csv(
    session_id: str,
    kind: ExportKind = Query(..., description="summary | trades | equity | drawdown"),
) -> Response:
    if kind not in EXPORT_KINDS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid CSV kind. Expected one of: {', '.join(EXPORT_KINDS)}",
        )
    session = _require(session_id)
    report = _build_export_report_or_http(session)
    try:
        payload = render_csv(report, kind)
    except ReportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = build_export_filename(
        symbol=session.symbol,
        kind=kind,
        extension="csv",
        generated_at=report.metadata.generated_at,
    )
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/sessions/{session_id}/report/export/pdf")
async def export_replay_report_pdf(session_id: str) -> Response:
    session = _require(session_id)
    report = _build_export_report_or_http(session)
    try:
        payload = render_pdf(report)
    except ReportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"PDF generation failed: {exc}"
        ) from exc
    filename = build_export_filename(
        symbol=session.symbol,
        kind="report",
        extension="pdf",
        generated_at=report.metadata.generated_at,
    )
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _require(session_id: str):
    session = get_replay_manager().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Replay session not found")
    return session
