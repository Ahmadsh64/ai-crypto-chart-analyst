"""Atomic analysis_snapshot + decision + trade_plan persistence (Phase 6.0.2)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.consistency import classify_consistency
from app.db.exceptions import (
    IdempotencyConflictError,
    PersistenceDisabledError,
    PersistenceUnavailableError,
)
from app.db.identity import new_analysis_run_id
from app.db.json_codec import content_hash, decimal_to_str, jsonable
from app.db.models.analysis import (
    AnalysisSession,
    AnalysisSnapshot,
    Decision,
    TradePlan,
)
from app.db.session import get_async_session_factory, is_persistence_active


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _as_dt(value: Any, default: datetime | None = None) -> datetime:
    if value is None:
        return default or datetime.now(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value).replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _tp_decimal_strings(payload: dict[str, Any] | None) -> list[str]:
    if not payload:
        return []
    raw = (
        payload.get("take_profit_prices")
        or payload.get("take_profit_targets")
        or payload.get("take_profits")
        or []
    )
    if isinstance(raw, dict):
        raw = raw.get("prices") or list(raw.values())
    out: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            price = item.get("price")
            s = decimal_to_str(price) if price is not None else None
        else:
            s = decimal_to_str(item)
        if s is not None:
            out.append(s)
    return out


@dataclass(slots=True)
class AnalysisPersistResult:
    analysis_run_id: str
    snapshot_id: uuid.UUID
    decision_row_id: uuid.UUID | None
    trade_plan_row_id: uuid.UUID | None
    consistency_status: str
    content_hash: str
    created: bool
    idempotent: bool
    analysis_session_id: uuid.UUID | None = None


async def get_or_create_analysis_session(
    session: AsyncSession,
    *,
    exchange: str,
    market_type: str,
    symbol: str,
    primary_timeframe: str | None = None,
    source: str = "chart_analyzer",
) -> uuid.UUID:
    """Return an active analysis_sessions row id (create if needed). Same TX."""
    existing = await session.scalar(
        select(AnalysisSession)
        .where(
            AnalysisSession.exchange == exchange,
            AnalysisSession.market_type == market_type,
            AnalysisSession.symbol == symbol,
            AnalysisSession.status == "active",
        )
        .order_by(AnalysisSession.created_at.desc())
        .limit(1)
    )
    if existing is not None:
        return existing.id
    row = AnalysisSession(
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        primary_timeframe=primary_timeframe,
        status="active",
        source=source,
    )
    session.add(row)
    await session.flush()
    return row.id


async def persist_analysis_bundle(
    *,
    exchange: str,
    market_type: str,
    symbol: str,
    decision: dict[str, Any] | None = None,
    trade_plan: dict[str, Any] | None = None,
    analysis_run_id: str | None = None,
    analysis_session_id: uuid.UUID | None = None,
    timeframe: str | None = None,
    snapshot_kind: str = "live_decision_bundle",
    configuration_versions: dict[str, Any] | None = None,
    data_freshness: str | None = None,
    session: AsyncSession | None = None,
    ensure_analysis_session: bool = True,
    session_source: str = "chart_analyzer",
) -> AnalysisPersistResult:
    """
    Atomically persist snapshot + optional decision/plan extracts for one run.

    Idempotent when the same analysis_run_id + content_hash already exists.
    Raises IdempotencyConflictError when the same run id has a different hash.
    No-ops gracefully only when persistence is disabled if session is not provided
    — callers should check is_persistence_active() first for soft skip.
    """
    if session is None and not is_persistence_active():
        raise PersistenceDisabledError("Persistence is disabled")

    run_id = analysis_run_id or new_analysis_run_id()
    decision_payload = jsonable(decision) if decision is not None else None
    plan_payload = jsonable(trade_plan) if trade_plan is not None else None

    consistency = classify_consistency(
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        decision_payload=decision if decision is not None else None,
        trade_plan_payload=trade_plan if trade_plan is not None else None,
    )

    decision_ts = (
        _as_dt(decision.get("analysis_timestamp") or decision.get("timestamp"))
        if decision
        else None
    )
    plan_ts = (
        _as_dt(
            trade_plan.get("analysis_timestamp") or trade_plan.get("timestamp")
        )
        if trade_plan
        else None
    )
    analysis_ts = decision_ts or plan_ts or datetime.now(timezone.utc)

    decision_text = (
        str(decision.get("decision"))
        if decision and decision.get("decision") is not None
        else (
            str(trade_plan.get("direction") or trade_plan.get("plan_status") or "UNKNOWN")
            if trade_plan
            else "UNKNOWN"
        )
    )

    # Decision-preferred numeric extracts
    entry_ref = _as_decimal(
        (decision or {}).get("entry_reference_price")
        if decision
        else (trade_plan or {}).get("entry_reference_price")
    )
    entry_low = _as_decimal(
        (decision or {}).get("entry_low")
        if decision
        else (trade_plan or {}).get("entry_low")
    )
    entry_high = _as_decimal(
        (decision or {}).get("entry_high")
        if decision
        else (trade_plan or {}).get("entry_high")
    )
    stop_loss = _as_decimal(
        (decision or {}).get("stop_loss_price")
        if decision
        else (trade_plan or {}).get("stop_loss_price")
        or (trade_plan or {}).get("stop_loss")
    )
    if decision:
        primary_rr = _as_decimal(
            decision.get("primary_rr") or decision.get("risk_reward")
        )
    else:
        primary_rr = _as_decimal(
            (trade_plan or {}).get("primary_rr")
            or (trade_plan or {}).get("risk_reward")
        )
    bullish = _as_decimal((decision or {}).get("bullish_score")) if decision else None
    bearish = _as_decimal((decision or {}).get("bearish_score")) if decision else None
    tp_prices = _tp_decimal_strings(decision) or _tp_decimal_strings(trade_plan)

    snapshot_payload = {
        "schema": "analysis-snapshot-db-v1",
        "analysis_run_id": run_id,
        "consistency_status": consistency,
        "decision_analysis_timestamp": (
            decision_ts.isoformat().replace("+00:00", "Z") if decision_ts else None
        ),
        "trade_plan_analysis_timestamp": (
            plan_ts.isoformat().replace("+00:00", "Z") if plan_ts else None
        ),
        "analysis_snapshot": {
            "decision": decision_text,
            "entry_reference_price": decimal_to_str(entry_ref),
            "stop_loss_price": decimal_to_str(stop_loss),
            "take_profit_prices": tp_prices,
        },
        "raw_decision": decision_payload,
        "raw_trade_plan": plan_payload,
    }
    c_hash = content_hash(snapshot_payload)
    config_versions = jsonable(configuration_versions or {})

    owns_session = session is None
    if owns_session:
        factory = get_async_session_factory()
        if factory is None:
            raise PersistenceUnavailableError("Session factory unavailable")
        session = factory()

    assert session is not None
    try:
        existing = await session.scalar(
            select(AnalysisSnapshot)
            .where(AnalysisSnapshot.analysis_run_id == run_id)
            .options(
                selectinload(AnalysisSnapshot.decision_row),
                selectinload(AnalysisSnapshot.trade_plan_row),
            )
        )
        if existing is not None:
            if existing.content_hash == c_hash:
                return AnalysisPersistResult(
                    analysis_run_id=run_id,
                    snapshot_id=existing.id,
                    decision_row_id=(
                        existing.decision_row.id if existing.decision_row else None
                    ),
                    trade_plan_row_id=(
                        existing.trade_plan_row.id if existing.trade_plan_row else None
                    ),
                    consistency_status=existing.consistency_status,
                    content_hash=existing.content_hash,
                    created=False,
                    idempotent=True,
                    analysis_session_id=existing.analysis_session_id,
                )
            raise IdempotencyConflictError(
                "analysis_run_id already persisted with a different content_hash",
                identity_key=run_id,
                existing_hash=existing.content_hash,
                incoming_hash=c_hash,
            )

        resolved_session_id = analysis_session_id
        if resolved_session_id is None and ensure_analysis_session:
            resolved_session_id = await get_or_create_analysis_session(
                session,
                exchange=exchange,
                market_type=market_type,
                symbol=symbol,
                primary_timeframe=timeframe
                or (decision or {}).get("timeframe")
                or (trade_plan or {}).get("timeframe"),
                source=session_source,
            )

        snap = AnalysisSnapshot(
            analysis_session_id=resolved_session_id,
            analysis_run_id=run_id,
            snapshot_kind=snapshot_kind,
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
            timeframe=timeframe
            or (decision or {}).get("timeframe")
            or (trade_plan or {}).get("timeframe"),
            analysis_timestamp=analysis_ts,
            decision_analysis_timestamp=decision_ts,
            trade_plan_analysis_timestamp=plan_ts,
            consistency_status=consistency,
            decision=decision_text,
            decision_id=(decision or {}).get("decision_id") if decision else None,
            plan_id=(trade_plan or {}).get("plan_id") if trade_plan else None,
            configuration_versions=config_versions,
            snapshot_schema_version="analysis-snapshot-db-v1",
            data_freshness=data_freshness,
            entry_reference_price=entry_ref,
            entry_low=entry_low,
            entry_high=entry_high,
            stop_loss_price=stop_loss,
            take_profit_prices=tp_prices,
            primary_rr=primary_rr,
            confluence_bullish=bullish,
            confluence_bearish=bearish,
            snapshot_payload=snapshot_payload,
            content_hash=c_hash,
        )
        session.add(snap)
        await session.flush()

        decision_row_id: uuid.UUID | None = None
        plan_row_id: uuid.UUID | None = None

        if decision is not None:
            d_row = Decision(
                analysis_snapshot_id=snap.id,
                analysis_run_id=run_id,
                decision_id=decision.get("decision_id"),
                decision=str(decision.get("decision") or decision_text),
                decision_reason=str(decision.get("decision_reason") or ""),
                lifecycle=(
                    str(decision["lifecycle"])
                    if decision.get("lifecycle") is not None
                    else None
                ),
                direction=(
                    str(decision["direction"])
                    if decision.get("direction") is not None
                    else None
                ),
                bullish_score=_as_decimal(decision.get("bullish_score")),
                bearish_score=_as_decimal(decision.get("bearish_score")),
                evidence_payload=jsonable(decision.get("evidence") or []),
                conflicts_payload=jsonable(decision.get("conflicts") or []),
                blocking_conditions=jsonable(
                    decision.get("blocking_conditions") or []
                ),
                configuration_version=str(
                    decision.get("configuration_version")
                    or decision.get("config_version")
                    or "unknown"
                ),
                analysis_timestamp=decision_ts or analysis_ts,
            )
            session.add(d_row)
            await session.flush()
            decision_row_id = d_row.id

        if trade_plan is not None:
            p_row = TradePlan(
                analysis_snapshot_id=snap.id,
                analysis_run_id=run_id,
                plan_id=trade_plan.get("plan_id"),
                direction=(
                    str(trade_plan["direction"])
                    if trade_plan.get("direction") is not None
                    else None
                ),
                plan_status=str(
                    trade_plan.get("plan_status")
                    or trade_plan.get("status")
                    or "unknown"
                ),
                entry_reference_price=_as_decimal(
                    trade_plan.get("entry_reference_price")
                ),
                entry_low=_as_decimal(trade_plan.get("entry_low")),
                entry_high=_as_decimal(trade_plan.get("entry_high")),
                stop_loss_price=_as_decimal(
                    trade_plan.get("stop_loss_price") or trade_plan.get("stop_loss")
                ),
                take_profit_targets=_tp_decimal_strings(trade_plan),
                primary_rr=_as_decimal(
                    trade_plan.get("primary_rr") or trade_plan.get("risk_reward")
                ),
                eligibility_payload=jsonable(
                    trade_plan.get("eligibility")
                    or trade_plan.get("eligibility_payload")
                    or {}
                ),
                plan_payload=plan_payload or {},
                configuration_version=str(
                    trade_plan.get("configuration_version")
                    or trade_plan.get("config_version")
                    or "unknown"
                ),
                analysis_timestamp=plan_ts or analysis_ts,
            )
            session.add(p_row)
            await session.flush()
            plan_row_id = p_row.id

        if owns_session:
            await session.commit()

        return AnalysisPersistResult(
            analysis_run_id=run_id,
            snapshot_id=snap.id,
            decision_row_id=decision_row_id,
            trade_plan_row_id=plan_row_id,
            consistency_status=consistency,
            content_hash=c_hash,
            created=True,
            idempotent=False,
            analysis_session_id=resolved_session_id,
        )
    except Exception:
        if owns_session:
            await session.rollback()
        raise
    finally:
        if owns_session:
            await session.close()
