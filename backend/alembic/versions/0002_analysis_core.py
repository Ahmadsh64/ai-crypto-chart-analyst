"""Create analysis_sessions and analysis_snapshots.

Revision ID: 0002_analysis_core
Revises: 0001_extensions
Create Date: 2026-11-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_analysis_core"
down_revision: Union[str, None] = "0001_extensions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analysis_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("market_type", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("primary_timeframe", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analysis_sessions_market_created",
        "analysis_sessions",
        ["exchange", "market_type", "symbol", sa.text("created_at DESC")],
        unique=False,
    )

    op.create_table(
        "analysis_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("analysis_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("analysis_run_id", sa.Text(), nullable=False),
        sa.Column("snapshot_kind", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("market_type", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("timeframe", sa.Text(), nullable=True),
        sa.Column("analysis_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "decision_analysis_timestamp",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "trade_plan_analysis_timestamp",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("consistency_status", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=True),
        sa.Column("plan_id", sa.Text(), nullable=True),
        sa.Column(
            "configuration_versions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("snapshot_schema_version", sa.Text(), nullable=False),
        sa.Column("data_freshness", sa.Text(), nullable=True),
        sa.Column("entry_reference_price", sa.Numeric(28, 12), nullable=True),
        sa.Column("entry_low", sa.Numeric(28, 12), nullable=True),
        sa.Column("entry_high", sa.Numeric(28, 12), nullable=True),
        sa.Column("stop_loss_price", sa.Numeric(28, 12), nullable=True),
        sa.Column(
            "take_profit_prices",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("primary_rr", sa.Numeric(18, 8), nullable=True),
        sa.Column("confluence_bullish", sa.Numeric(10, 4), nullable=True),
        sa.Column("confluence_bearish", sa.Numeric(10, 4), nullable=True),
        sa.Column(
            "snapshot_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "consistency_status IN ("
            "'ALIGNED','DUAL_FETCH_DIVERGED','DECISION_ONLY',"
            "'PLAN_ONLY','INSUFFICIENT_PROVENANCE')",
            name="ck_analysis_snapshots_consistency",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_session_id"],
            ["analysis_sessions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_run_id", name="uq_analysis_snapshots_run_id"),
        sa.UniqueConstraint(
            "snapshot_kind",
            "content_hash",
            name="uq_analysis_snapshots_kind_hash",
        ),
    )
    op.create_index(
        "ix_analysis_snapshots_market_ts",
        "analysis_snapshots",
        ["exchange", "market_type", "symbol", sa.text("analysis_timestamp DESC")],
        unique=False,
    )
    op.create_index(
        "ix_analysis_snapshots_consistency_ts",
        "analysis_snapshots",
        ["consistency_status", sa.text("analysis_timestamp DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_analysis_snapshots_consistency_ts", table_name="analysis_snapshots"
    )
    op.drop_index("ix_analysis_snapshots_market_ts", table_name="analysis_snapshots")
    op.drop_table("analysis_snapshots")
    op.drop_index(
        "ix_analysis_sessions_market_created", table_name="analysis_sessions"
    )
    op.drop_table("analysis_sessions")
