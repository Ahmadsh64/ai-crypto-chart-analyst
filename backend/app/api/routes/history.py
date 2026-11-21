"""Read-only Analysis History REST endpoints (Phase 6.0.3.1).

Reads persisted Analyze records only — never calls live market providers
or re-runs Decision / Trade Plan engines.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from app.api.schemas.history import (
    AnalysisHistoryDetailResponse,
    AnalysisHistoryListItem,
    AnalysisHistoryListResponse,
)
from app.db.exceptions import PersistenceDisabledError, PersistenceUnavailableError
from app.db.repositories.history import AnalysisHistoryRepository
from app.db.session import get_async_session_factory, is_persistence_active

router = APIRouter(prefix="/history", tags=["history"])

ALLOWED_DECISIONS = frozenset({"LONG", "SHORT", "WAIT", "NO TRADE"})
ALLOWED_CONSISTENCY = frozenset(
    {
        "ALIGNED",
        "DUAL_FETCH_DIVERGED",
        "DECISION_ONLY",
        "PLAN_ONLY",
        "INSUFFICIENT_PROVENANCE",
    }
)


def _history_unavailable(exc: Exception | None = None) -> HTTPException:
    """Safe 503 — never expose SQL, URLs, or credentials."""
    if isinstance(exc, PersistenceDisabledError):
        return HTTPException(
            status_code=503,
            detail={
                "code": "PERSISTENCE_DISABLED",
                "message": "Analysis history is unavailable because persistence is disabled.",
            },
        )
    return HTTPException(
        status_code=503,
        detail={
            "code": "DATABASE_UNAVAILABLE",
            "message": "Analysis history is temporarily unavailable.",
        },
    )


def _normalize_symbol(symbol: str | None) -> str | None:
    if not symbol:
        return None
    s = symbol.strip().upper().replace("-", "/")
    if "/" not in s and s.endswith("USDT") and len(s) > 4:
        s = f"{s[:-4]}/USDT"
    elif "/" not in s and s.endswith("USD") and len(s) > 3:
        s = f"{s[:-3]}/USD"
    return s


async def _open_session():
    if not is_persistence_active():
        raise PersistenceDisabledError("Persistence is disabled")
    factory = get_async_session_factory()
    if factory is None:
        raise PersistenceUnavailableError("Session factory not initialized")
    return factory()


@router.get("/analyses", response_model=AnalysisHistoryListResponse)
async def list_analyses(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    exchange: Annotated[str | None, Query()] = None,
    market_type: Annotated[str | None, Query()] = None,
    symbol: Annotated[str | None, Query()] = None,
    timeframe: Annotated[str | None, Query()] = None,
    decision: Annotated[str | None, Query()] = None,
    consistency_status: Annotated[str | None, Query()] = None,
    from_ts: Annotated[
        datetime | None,
        Query(alias="from", description="Inclusive analysis_timestamp lower bound (UTC)"),
    ] = None,
    to_ts: Annotated[
        datetime | None,
        Query(alias="to", description="Inclusive analysis_timestamp upper bound (UTC)"),
    ] = None,
) -> AnalysisHistoryListResponse:
    """Paginated list of persisted Analyze snapshots (read-only)."""
    decision_norm = decision.strip().upper() if decision else None
    if decision_norm and decision_norm not in ALLOWED_DECISIONS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_DECISION_FILTER",
                "message": f"decision must be one of: {', '.join(sorted(ALLOWED_DECISIONS))}",
            },
        )
    consistency_norm = consistency_status.strip().upper() if consistency_status else None
    if consistency_norm and consistency_norm not in ALLOWED_CONSISTENCY:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_CONSISTENCY_FILTER",
                "message": (
                    "consistency_status must be one of: "
                    + ", ".join(sorted(ALLOWED_CONSISTENCY))
                ),
            },
        )

    session = None
    try:
        session = await _open_session()
        repo = AnalysisHistoryRepository(session)
        rows, total = await repo.list_analyses(
            limit=limit,
            offset=offset,
            exchange=exchange,
            market_type=market_type,
            symbol=_normalize_symbol(symbol),
            timeframe=timeframe,
            decision=decision_norm,
            consistency_status=consistency_norm,
            from_ts=from_ts,
            to_ts=to_ts,
        )
        items = [
            AnalysisHistoryListItem.model_validate(repo.to_list_item(row))
            for row in rows
        ]
        return AnalysisHistoryListResponse(
            items=items, total=total, limit=limit, offset=offset
        )
    except (PersistenceDisabledError, PersistenceUnavailableError) as exc:
        raise _history_unavailable(exc) from exc
    except SQLAlchemyError as exc:
        raise _history_unavailable(exc) from exc
    finally:
        if session is not None:
            await session.close()


async def _detail_for_run(analysis_run_id: str) -> AnalysisHistoryDetailResponse:
    session = None
    try:
        session = await _open_session()
        repo = AnalysisHistoryRepository(session)
        row = await repo.get_by_run_id(analysis_run_id)
        if row is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "ANALYSIS_NOT_FOUND",
                    "message": "No persisted analysis found for this analysis_run_id.",
                },
            )
        return AnalysisHistoryDetailResponse.model_validate(repo.to_detail(row))
    except HTTPException:
        raise
    except (PersistenceDisabledError, PersistenceUnavailableError) as exc:
        raise _history_unavailable(exc) from exc
    except SQLAlchemyError as exc:
        raise _history_unavailable(exc) from exc
    finally:
        if session is not None:
            await session.close()


@router.get(
    "/analyses/by-run/{analysis_run_id}",
    response_model=AnalysisHistoryDetailResponse,
)
async def get_analysis_by_run(
    analysis_run_id: str,
) -> AnalysisHistoryDetailResponse:
    """Detail lookup by orchestration analysis_run_id (preferred)."""
    return await _detail_for_run(analysis_run_id)


@router.get(
    "/analyses/{analysis_run_id}",
    response_model=AnalysisHistoryDetailResponse,
)
async def get_analysis_detail(
    analysis_run_id: str,
) -> AnalysisHistoryDetailResponse:
    """
    Detail by analysis_run_id (same as /by-run/…).

    If the path looks like a snapshot UUID and no run matches, falls back to
    snapshot primary key lookup for API-design compatibility.
    """
    session = None
    try:
        session = await _open_session()
        repo = AnalysisHistoryRepository(session)
        row = await repo.get_by_run_id(analysis_run_id)
        if row is None:
            row = await repo.get_by_snapshot_id(analysis_run_id)
        if row is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "ANALYSIS_NOT_FOUND",
                    "message": "No persisted analysis found for this identifier.",
                },
            )
        return AnalysisHistoryDetailResponse.model_validate(repo.to_detail(row))
    except HTTPException:
        raise
    except (PersistenceDisabledError, PersistenceUnavailableError) as exc:
        raise _history_unavailable(exc) from exc
    except SQLAlchemyError as exc:
        raise _history_unavailable(exc) from exc
    finally:
        if session is not None:
            await session.close()
