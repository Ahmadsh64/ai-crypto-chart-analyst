"""Read-only analysis history repository (Phase 6.0.3.1).

Reads persisted Analyze records only — never recomputes Decision/Trade Plan.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.analysis import AnalysisSession, AnalysisSnapshot, Decision, TradePlan


def _dec_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _tp_list(value: list[Any] | None) -> list[str]:
    if not value:
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, Decimal):
            out.append(format(item, "f"))
        elif item is None:
            continue
        else:
            out.append(str(item))
    return out


class AnalysisHistoryRepository:
    """Query analysis_snapshots (+ related rows) for History API."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _base_filters(
        self,
        *,
        exchange: str | None,
        market_type: str | None,
        symbol: str | None,
        timeframe: str | None,
        decision: str | None,
        consistency_status: str | None,
        from_ts: datetime | None,
        to_ts: datetime | None,
    ) -> list[Any]:
        clauses: list[Any] = []
        if exchange:
            clauses.append(AnalysisSnapshot.exchange == exchange.strip().lower())
        if market_type:
            clauses.append(AnalysisSnapshot.market_type == market_type.strip().lower())
        if symbol:
            # Normalize BTCUSDT → BTC/USDT-style: match exact stored symbol (typically BTC/USDT)
            clauses.append(AnalysisSnapshot.symbol == symbol.strip().upper())
        if timeframe:
            clauses.append(AnalysisSnapshot.timeframe == timeframe.strip())
        if decision:
            clauses.append(AnalysisSnapshot.decision == decision.strip().upper())
        if consistency_status:
            clauses.append(
                AnalysisSnapshot.consistency_status == consistency_status.strip().upper()
            )
        if from_ts is not None:
            clauses.append(AnalysisSnapshot.analysis_timestamp >= from_ts)
        if to_ts is not None:
            clauses.append(AnalysisSnapshot.analysis_timestamp <= to_ts)
        return clauses

    async def list_analyses(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        exchange: str | None = None,
        market_type: str | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        decision: str | None = None,
        consistency_status: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
    ) -> tuple[list[AnalysisSnapshot], int]:
        """Return (rows, total) with stable order: analysis_timestamp DESC, id DESC."""
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        clauses = self._base_filters(
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
            timeframe=timeframe,
            decision=decision,
            consistency_status=consistency_status,
            from_ts=from_ts,
            to_ts=to_ts,
        )

        count_stmt: Select[Any] = select(func.count()).select_from(AnalysisSnapshot)
        list_stmt: Select[Any] = select(AnalysisSnapshot)
        for clause in clauses:
            count_stmt = count_stmt.where(clause)
            list_stmt = list_stmt.where(clause)

        total = int((await self._session.execute(count_stmt)).scalar_one())
        list_stmt = (
            list_stmt.order_by(
                AnalysisSnapshot.analysis_timestamp.desc(),
                AnalysisSnapshot.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        rows = list((await self._session.execute(list_stmt)).scalars().all())
        return rows, total

    def _detail_options(self) -> list[Any]:
        return [
            selectinload(AnalysisSnapshot.session),
            selectinload(AnalysisSnapshot.decision_row),
            selectinload(AnalysisSnapshot.trade_plan_row),
        ]

    async def get_by_run_id(self, analysis_run_id: str) -> AnalysisSnapshot | None:
        """Load one snapshot with session + decision + trade_plan extracts."""
        run_id = (analysis_run_id or "").strip()
        if not run_id:
            return None
        stmt = (
            select(AnalysisSnapshot)
            .where(AnalysisSnapshot.analysis_run_id == run_id)
            .options(*self._detail_options())
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_snapshot_id(self, snapshot_id: str) -> AnalysisSnapshot | None:
        """Load by analysis_snapshots.id (UUID)."""
        raw = (snapshot_id or "").strip()
        if not raw:
            return None
        try:
            sid = UUID(raw)
        except ValueError:
            return None
        stmt = (
            select(AnalysisSnapshot)
            .where(AnalysisSnapshot.id == sid)
            .options(*self._detail_options())
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    def to_list_item(row: AnalysisSnapshot) -> dict[str, Any]:
        return {
            "analysis_run_id": row.analysis_run_id,
            "snapshot_id": str(row.id),
            "analysis_session_id": (
                str(row.analysis_session_id) if row.analysis_session_id else None
            ),
            "exchange": row.exchange,
            "market_type": row.market_type,
            "symbol": row.symbol,
            "timeframe": row.timeframe,
            "analysis_timestamp": row.analysis_timestamp,
            "decision": row.decision,
            "consistency_status": row.consistency_status,
            "decision_analysis_timestamp": row.decision_analysis_timestamp,
            "trade_plan_analysis_timestamp": row.trade_plan_analysis_timestamp,
            "entry_reference_price": _dec_str(row.entry_reference_price),
            "stop_loss_price": _dec_str(row.stop_loss_price),
            "take_profit_prices": _tp_list(row.take_profit_prices),
            "primary_rr": _dec_str(row.primary_rr),
            "data_freshness": row.data_freshness,
            "created_at": row.created_at,
        }

    @staticmethod
    def to_detail(row: AnalysisSnapshot) -> dict[str, Any]:
        session: AnalysisSession | None = row.session
        decision_row: Decision | None = row.decision_row
        plan_row: TradePlan | None = row.trade_plan_row
        session_summary = None
        if session is not None:
            session_summary = {
                "id": str(session.id),
                "exchange": session.exchange,
                "market_type": session.market_type,
                "symbol": session.symbol,
                "primary_timeframe": session.primary_timeframe,
                "status": session.status,
                "source": session.source,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            }
        return {
            "analysis_run_id": row.analysis_run_id,
            "snapshot_id": str(row.id),
            "consistency_status": row.consistency_status,
            "snapshot_kind": row.snapshot_kind,
            "exchange": row.exchange,
            "market_type": row.market_type,
            "symbol": row.symbol,
            "timeframe": row.timeframe,
            "analysis_timestamp": row.analysis_timestamp,
            "decision_analysis_timestamp": row.decision_analysis_timestamp,
            "trade_plan_analysis_timestamp": row.trade_plan_analysis_timestamp,
            "decision": row.decision,
            "decision_id": row.decision_id,
            "plan_id": row.plan_id,
            "configuration_versions": dict(row.configuration_versions or {}),
            "snapshot_schema_version": row.snapshot_schema_version,
            "data_freshness": row.data_freshness,
            "entry_reference_price": _dec_str(row.entry_reference_price),
            "entry_low": _dec_str(row.entry_low),
            "entry_high": _dec_str(row.entry_high),
            "stop_loss_price": _dec_str(row.stop_loss_price),
            "take_profit_prices": _tp_list(row.take_profit_prices),
            "primary_rr": _dec_str(row.primary_rr),
            "confluence_bullish": _dec_str(row.confluence_bullish),
            "confluence_bearish": _dec_str(row.confluence_bearish),
            "content_hash": row.content_hash,
            "created_at": row.created_at,
            "session": session_summary,
            "snapshot_payload": dict(row.snapshot_payload or {}),
            # Decision/TradePlan rows store typed columns + JSONB extracts (not a single
            # `.payload` field). Prefer raw snapshot embeds when present.
            "decision_extract": (
                dict(row.snapshot_payload.get("raw_decision") or {})
                if isinstance(row.snapshot_payload, dict)
                and row.snapshot_payload.get("raw_decision")
                else (
                    {
                        "decision": decision_row.decision,
                        "decision_reason": decision_row.decision_reason,
                        "lifecycle": decision_row.lifecycle,
                        "direction": decision_row.direction,
                        "decision_id": decision_row.decision_id,
                        "bullish_score": _dec_str(decision_row.bullish_score),
                        "bearish_score": _dec_str(decision_row.bearish_score),
                        "evidence": list(decision_row.evidence_payload or []),
                        "conflicts": list(decision_row.conflicts_payload or []),
                        "blocking_conditions": list(
                            decision_row.blocking_conditions or []
                        ),
                        "configuration_version": decision_row.configuration_version,
                        "analysis_timestamp": decision_row.analysis_timestamp,
                    }
                    if decision_row is not None
                    else None
                )
            ),
            "trade_plan_extract": (
                dict(row.snapshot_payload.get("raw_trade_plan") or {})
                if isinstance(row.snapshot_payload, dict)
                and row.snapshot_payload.get("raw_trade_plan")
                else (
                    dict(plan_row.plan_payload)
                    if plan_row is not None and plan_row.plan_payload is not None
                    else None
                )
            ),
        }


__all__ = ["AnalysisHistoryRepository"]
