"""Analysis session / snapshot / decision / trade_plan ORM (Phase 6.0.2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    desc,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

NUMERIC_PRICE = Numeric(28, 12)
NUMERIC_RR = Numeric(18, 8)
NUMERIC_SCORE = Numeric(10, 4)

CONSISTENCY_STATUSES = (
    "ALIGNED",
    "DUAL_FETCH_DIVERGED",
    "DECISION_ONLY",
    "PLAN_ONLY",
    "INSUFFICIENT_PROVENANCE",
)


class AnalysisSession(Base):
    __tablename__ = "analysis_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    market_type: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    primary_timeframe: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    source: Mapped[str] = mapped_column(Text, nullable=False, default="chart_analyzer")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    snapshots: Mapped[list[AnalysisSnapshot]] = relationship(
        back_populates="session",
        passive_deletes=True,
    )

    __table_args__ = (
        Index(
            "ix_analysis_sessions_market_created",
            "exchange",
            "market_type",
            "symbol",
            desc("created_at"),
        ),
    )


class AnalysisSnapshot(Base):
    __tablename__ = "analysis_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    analysis_session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    analysis_run_id: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_kind: Mapped[str] = mapped_column(Text, nullable=False)
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    market_type: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    timeframe: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    analysis_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    decision_analysis_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trade_plan_analysis_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consistency_status: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    decision_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    plan_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    configuration_versions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False
    )
    snapshot_schema_version: Mapped[str] = mapped_column(
        Text, nullable=False, default="analysis-snapshot-db-v1"
    )
    data_freshness: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    entry_reference_price: Mapped[Optional[Decimal]] = mapped_column(
        NUMERIC_PRICE, nullable=True
    )
    entry_low: Mapped[Optional[Decimal]] = mapped_column(NUMERIC_PRICE, nullable=True)
    entry_high: Mapped[Optional[Decimal]] = mapped_column(NUMERIC_PRICE, nullable=True)
    stop_loss_price: Mapped[Optional[Decimal]] = mapped_column(
        NUMERIC_PRICE, nullable=True
    )
    take_profit_prices: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    primary_rr: Mapped[Optional[Decimal]] = mapped_column(NUMERIC_RR, nullable=True)
    confluence_bullish: Mapped[Optional[Decimal]] = mapped_column(
        NUMERIC_SCORE, nullable=True
    )
    confluence_bearish: Mapped[Optional[Decimal]] = mapped_column(
        NUMERIC_SCORE, nullable=True
    )
    snapshot_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    session: Mapped[Optional[AnalysisSession]] = relationship(
        back_populates="snapshots"
    )
    decision_row: Mapped[Optional[Decision]] = relationship(
        back_populates="snapshot",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    trade_plan_row: Mapped[Optional[TradePlan]] = relationship(
        back_populates="snapshot",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("analysis_run_id", name="uq_analysis_snapshots_run_id"),
        UniqueConstraint(
            "snapshot_kind",
            "content_hash",
            name="uq_analysis_snapshots_kind_hash",
        ),
        CheckConstraint(
            "consistency_status IN ("
            "'ALIGNED','DUAL_FETCH_DIVERGED','DECISION_ONLY',"
            "'PLAN_ONLY','INSUFFICIENT_PROVENANCE')",
            name="ck_analysis_snapshots_consistency",
        ),
        Index(
            "ix_analysis_snapshots_market_ts",
            "exchange",
            "market_type",
            "symbol",
            desc("analysis_timestamp"),
        ),
        Index(
            "ix_analysis_snapshots_consistency_ts",
            "consistency_status",
            desc("analysis_timestamp"),
        ),
    )


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    analysis_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    analysis_run_id: Mapped[str] = mapped_column(Text, nullable=False)
    decision_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    decision_reason: Mapped[str] = mapped_column(Text, nullable=False)
    lifecycle: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    direction: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bullish_score: Mapped[Optional[Decimal]] = mapped_column(
        NUMERIC_SCORE, nullable=True
    )
    bearish_score: Mapped[Optional[Decimal]] = mapped_column(
        NUMERIC_SCORE, nullable=True
    )
    evidence_payload: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    conflicts_payload: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    blocking_conditions: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    configuration_version: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    snapshot: Mapped[AnalysisSnapshot] = relationship(back_populates="decision_row")

    __table_args__ = (
        UniqueConstraint("analysis_run_id", name="uq_decisions_analysis_run_id"),
        Index(
            "uq_decisions_decision_id",
            "decision_id",
            unique=True,
            postgresql_where=text("decision_id IS NOT NULL"),
        ),
        Index("ix_decisions_analysis_snapshot_id", "analysis_snapshot_id"),
        Index("ix_decisions_analysis_run_id", "analysis_run_id"),
    )


class TradePlan(Base):
    __tablename__ = "trade_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    analysis_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    analysis_run_id: Mapped[str] = mapped_column(Text, nullable=False)
    plan_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    direction: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    plan_status: Mapped[str] = mapped_column(Text, nullable=False)
    entry_reference_price: Mapped[Optional[Decimal]] = mapped_column(
        NUMERIC_PRICE, nullable=True
    )
    entry_low: Mapped[Optional[Decimal]] = mapped_column(NUMERIC_PRICE, nullable=True)
    entry_high: Mapped[Optional[Decimal]] = mapped_column(NUMERIC_PRICE, nullable=True)
    stop_loss_price: Mapped[Optional[Decimal]] = mapped_column(
        NUMERIC_PRICE, nullable=True
    )
    take_profit_targets: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    primary_rr: Mapped[Optional[Decimal]] = mapped_column(NUMERIC_RR, nullable=True)
    eligibility_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    plan_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    configuration_version: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    snapshot: Mapped[AnalysisSnapshot] = relationship(back_populates="trade_plan_row")

    __table_args__ = (
        UniqueConstraint("analysis_run_id", name="uq_trade_plans_analysis_run_id"),
        Index(
            "uq_trade_plans_plan_id",
            "plan_id",
            unique=True,
            postgresql_where=text("plan_id IS NOT NULL"),
        ),
        Index("ix_trade_plans_analysis_snapshot_id", "analysis_snapshot_id"),
        Index("ix_trade_plans_analysis_run_id", "analysis_run_id"),
    )
