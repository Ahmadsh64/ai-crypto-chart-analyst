"""Create isolated scanner_runs and market_opportunities tables (Phase 5.5).

Revision ID: 0004_scanner_persistence
Revises: 0003_decisions_trade_plans
Create Date: 2026-11-20

Additive only — does not alter analysis_sessions, analysis_snapshots,
decisions, or trade_plans.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_scanner_persistence"
down_revision: Union[str, None] = "0003_decisions_trade_plans"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scanner_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("scan_id", sa.Text(), nullable=False),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Numeric(12, 3), nullable=True),
        sa.Column(
            "exchanges",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "market_types",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "execution_timeframes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("pairs_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pairs_eligible", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pairs_selected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pairs_scanned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pairs_partial", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pairs_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "timeframe_analyses_attempted",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "timeframe_analyses_completed",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "timeframe_analyses_failed",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "opportunities_found", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("ready_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("long_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("short_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ranking_method", sa.Text(), nullable=True),
        sa.Column(
            "per_market",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "excluded_sample",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "errors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "config_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("config_version", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ("
            "'running','completed','completed_partial','failed','skipped')",
            name="ck_scanner_runs_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scan_id", name="uq_scanner_runs_scan_id"),
    )
    op.create_index(
        "ix_scanner_runs_started_at",
        "scanner_runs",
        [sa.text("started_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_scanner_runs_status_started",
        "scanner_runs",
        ["status", sa.text("started_at DESC")],
        unique=False,
    )

    op.create_table(
        "market_opportunities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("opportunity_id", sa.Text(), nullable=False),
        sa.Column("slot_key", sa.Text(), nullable=False),
        sa.Column("setup_fingerprint", sa.Text(), nullable=False),
        sa.Column("setup_generation", sa.Integer(), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("market_type", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("execution_timeframe", sa.Text(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=True),
        sa.Column("decision", sa.Text(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("previous_status", sa.Text(), nullable=True),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status_history",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("engine_lifecycle", sa.Text(), nullable=True),
        sa.Column("current_price", sa.Numeric(28, 12), nullable=True),
        sa.Column("price_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("price_source", sa.Text(), nullable=True),
        sa.Column("entry_reference", sa.Numeric(28, 12), nullable=True),
        sa.Column("entry_low", sa.Numeric(28, 12), nullable=True),
        sa.Column("entry_high", sa.Numeric(28, 12), nullable=True),
        sa.Column("stop_loss", sa.Numeric(28, 12), nullable=True),
        sa.Column("tp1", sa.Numeric(28, 12), nullable=True),
        sa.Column("tp2", sa.Numeric(28, 12), nullable=True),
        sa.Column("tp3", sa.Numeric(28, 12), nullable=True),
        sa.Column("tp1_available", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("tp2_available", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("tp3_available", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("primary_rr", sa.Numeric(18, 8), nullable=True),
        sa.Column("confluence_score", sa.Numeric(10, 4), nullable=True),
        sa.Column("confluence_bullish", sa.Numeric(10, 4), nullable=True),
        sa.Column("confluence_bearish", sa.Numeric(10, 4), nullable=True),
        sa.Column("entry_distance_pct", sa.Numeric(18, 8), nullable=True),
        sa.Column("quote_volume_24h", sa.Numeric(28, 8), nullable=True),
        sa.Column("actionable", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "supporting_evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "blocking_conditions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("invalidation_reason", sa.Text(), nullable=True),
        sa.Column("expiration_reason", sa.Text(), nullable=True),
        sa.Column("decision_id", sa.Text(), nullable=True),
        sa.Column("trade_plan_id", sa.Text(), nullable=True),
        sa.Column("analysis_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_scan_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rank_score", sa.Numeric(18, 8), nullable=True),
        sa.Column("rank_explanation", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("planned_not_fills_note", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ("
            "'READY','APPROACHING_ENTRY','WAITING',"
            "'INVALIDATED','EXPIRED','DATA_UNAVAILABLE')",
            name="ck_market_opportunities_status",
        ),
        sa.CheckConstraint(
            "decision IS NULL OR decision IN ('LONG','SHORT','WAIT','NO TRADE')",
            name="ck_market_opportunities_decision",
        ),
        sa.CheckConstraint(
            "direction IS NULL OR direction IN ('LONG','SHORT')",
            name="ck_market_opportunities_direction",
        ),
        sa.ForeignKeyConstraint(
            ["last_scan_run_id"],
            ["scanner_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "opportunity_id", name="uq_market_opportunities_opportunity_id"
        ),
        sa.UniqueConstraint(
            "slot_key",
            "setup_generation",
            name="uq_market_opportunities_slot_generation",
        ),
    )
    op.create_index(
        "uq_market_opportunities_one_open_per_slot",
        "market_opportunities",
        ["slot_key"],
        unique=True,
        postgresql_where=sa.text("is_open = true"),
    )
    op.create_index(
        "ix_market_opportunities_lookup",
        "market_opportunities",
        ["exchange", "market_type", "symbol", "execution_timeframe"],
        unique=False,
    )
    op.create_index(
        "ix_market_opportunities_status_eval",
        "market_opportunities",
        ["status", sa.text("last_evaluated_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_market_opportunities_actionable",
        "market_opportunities",
        ["actionable", sa.text("confluence_score DESC")],
        unique=False,
        postgresql_where=sa.text("is_open = true"),
    )
    op.create_index(
        "ix_market_opportunities_last_scan",
        "market_opportunities",
        ["last_scan_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_market_opportunities_last_scan", table_name="market_opportunities")
    op.drop_index(
        "ix_market_opportunities_actionable", table_name="market_opportunities"
    )
    op.drop_index(
        "ix_market_opportunities_status_eval", table_name="market_opportunities"
    )
    op.drop_index("ix_market_opportunities_lookup", table_name="market_opportunities")
    op.drop_index(
        "uq_market_opportunities_one_open_per_slot",
        table_name="market_opportunities",
    )
    op.drop_table("market_opportunities")
    op.drop_index("ix_scanner_runs_status_started", table_name="scanner_runs")
    op.drop_index("ix_scanner_runs_started_at", table_name="scanner_runs")
    op.drop_table("scanner_runs")
