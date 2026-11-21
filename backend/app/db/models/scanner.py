"""Scanner persistence ORM (Phase 5.5) — isolated from Phase 6.0.3 analysis tables."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
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
NUMERIC_VOLUME = Numeric(28, 8)
NUMERIC_DURATION = Numeric(12, 3)

SCANNER_CONFIG_VERSION = "scanner-persist-v1"


class ScannerRun(Base):
    __tablename__ = "scanner_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    scan_id: Mapped[str] = mapped_column(Text, nullable=False)
    trigger: Mapped[str] = mapped_column(Text, nullable=False, default="manual")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_seconds: Mapped[Optional[Decimal]] = mapped_column(
        NUMERIC_DURATION, nullable=True
    )
    exchanges: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    market_types: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    execution_timeframes: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    pairs_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pairs_eligible: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pairs_selected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pairs_scanned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pairs_partial: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pairs_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timeframe_analyses_attempted: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    timeframe_analyses_completed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    timeframe_analyses_failed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    opportunities_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ready_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    long_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    short_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ranking_method: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    per_market: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    excluded_sample: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    errors: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    config_version: Mapped[str] = mapped_column(
        Text, nullable=False, default=SCANNER_CONFIG_VERSION
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    opportunities: Mapped[list["MarketOpportunityRow"]] = relationship(
        back_populates="last_scan_run",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("scan_id", name="uq_scanner_runs_scan_id"),
        CheckConstraint(
            "status IN ("
            "'running','completed','completed_partial','failed','skipped')",
            name="ck_scanner_runs_status",
        ),
        Index("ix_scanner_runs_started_at", desc("started_at")),
        Index("ix_scanner_runs_status_started", "status", desc("started_at")),
    )


class MarketOpportunityRow(Base):
    __tablename__ = "market_opportunities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    opportunity_id: Mapped[str] = mapped_column(Text, nullable=False)
    slot_key: Mapped[str] = mapped_column(Text, nullable=False)
    setup_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    setup_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    market_type: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    execution_timeframe: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decision: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decision_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    previous_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status_changed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status_history: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    engine_lifecycle: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    current_price: Mapped[Optional[Decimal]] = mapped_column(NUMERIC_PRICE, nullable=True)
    price_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    price_source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    entry_reference: Mapped[Optional[Decimal]] = mapped_column(
        NUMERIC_PRICE, nullable=True
    )
    entry_low: Mapped[Optional[Decimal]] = mapped_column(NUMERIC_PRICE, nullable=True)
    entry_high: Mapped[Optional[Decimal]] = mapped_column(NUMERIC_PRICE, nullable=True)
    stop_loss: Mapped[Optional[Decimal]] = mapped_column(NUMERIC_PRICE, nullable=True)
    tp1: Mapped[Optional[Decimal]] = mapped_column(NUMERIC_PRICE, nullable=True)
    tp2: Mapped[Optional[Decimal]] = mapped_column(NUMERIC_PRICE, nullable=True)
    tp3: Mapped[Optional[Decimal]] = mapped_column(NUMERIC_PRICE, nullable=True)
    tp1_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tp2_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tp3_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    primary_rr: Mapped[Optional[Decimal]] = mapped_column(NUMERIC_RR, nullable=True)
    confluence_score: Mapped[Optional[Decimal]] = mapped_column(
        NUMERIC_SCORE, nullable=True
    )
    confluence_bullish: Mapped[Optional[Decimal]] = mapped_column(
        NUMERIC_SCORE, nullable=True
    )
    confluence_bearish: Mapped[Optional[Decimal]] = mapped_column(
        NUMERIC_SCORE, nullable=True
    )
    entry_distance_pct: Mapped[Optional[Decimal]] = mapped_column(
        NUMERIC_RR, nullable=True
    )
    quote_volume_24h: Mapped[Optional[Decimal]] = mapped_column(
        NUMERIC_VOLUME, nullable=True
    )
    actionable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supporting_evidence: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    blocking_conditions: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    invalidation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expiration_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decision_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trade_plan_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    analysis_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_scan_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scanner_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    rank_score: Mapped[Optional[Decimal]] = mapped_column(NUMERIC_RR, nullable=True)
    rank_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    planned_not_fills_note: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=(
            "Planned analytical levels from the deterministic engine — not executed fills."
        ),
    )
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

    last_scan_run: Mapped[Optional[ScannerRun]] = relationship(
        back_populates="opportunities"
    )

    __table_args__ = (
        UniqueConstraint("opportunity_id", name="uq_market_opportunities_opportunity_id"),
        UniqueConstraint(
            "slot_key",
            "setup_generation",
            name="uq_market_opportunities_slot_generation",
        ),
        Index(
            "uq_market_opportunities_one_open_per_slot",
            "slot_key",
            unique=True,
            postgresql_where=text("is_open = true"),
        ),
        CheckConstraint(
            "status IN ("
            "'READY','APPROACHING_ENTRY','WAITING',"
            "'INVALIDATED','EXPIRED','DATA_UNAVAILABLE')",
            name="ck_market_opportunities_status",
        ),
        CheckConstraint(
            "decision IS NULL OR decision IN ('LONG','SHORT','WAIT','NO TRADE')",
            name="ck_market_opportunities_decision",
        ),
        CheckConstraint(
            "direction IS NULL OR direction IN ('LONG','SHORT')",
            name="ck_market_opportunities_direction",
        ),
        Index(
            "ix_market_opportunities_lookup",
            "exchange",
            "market_type",
            "symbol",
            "execution_timeframe",
        ),
        Index(
            "ix_market_opportunities_status_eval",
            "status",
            desc("last_evaluated_at"),
        ),
        Index(
            "ix_market_opportunities_actionable",
            "actionable",
            desc("confluence_score"),
            postgresql_where=text("is_open = true"),
        ),
        Index("ix_market_opportunities_last_scan", "last_scan_run_id"),
    )
