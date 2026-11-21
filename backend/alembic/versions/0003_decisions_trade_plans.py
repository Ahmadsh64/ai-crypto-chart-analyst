"""Create decisions and trade_plans with RESTRICT FKs and analysis_run_id UKs.

Revision ID: 0003_decisions_trade_plans
Revises: 0002_analysis_core
Create Date: 2026-11-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_decisions_trade_plans"
down_revision: Union[str, None] = "0002_analysis_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "decisions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("analysis_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_run_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=True),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=False),
        sa.Column("lifecycle", sa.Text(), nullable=True),
        sa.Column("direction", sa.Text(), nullable=True),
        sa.Column("bullish_score", sa.Numeric(10, 4), nullable=True),
        sa.Column("bearish_score", sa.Numeric(10, 4), nullable=True),
        sa.Column(
            "evidence_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "conflicts_payload",
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
        sa.Column("configuration_version", sa.Text(), nullable=False),
        sa.Column("analysis_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["analysis_snapshot_id"],
            ["analysis_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_run_id", name="uq_decisions_analysis_run_id"),
    )
    op.create_index(
        "uq_decisions_decision_id",
        "decisions",
        ["decision_id"],
        unique=True,
        postgresql_where=sa.text("decision_id IS NOT NULL"),
    )
    op.create_index(
        "ix_decisions_analysis_snapshot_id",
        "decisions",
        ["analysis_snapshot_id"],
        unique=False,
    )
    op.create_index(
        "ix_decisions_analysis_run_id",
        "decisions",
        ["analysis_run_id"],
        unique=False,
    )

    op.create_table(
        "trade_plans",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("analysis_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_run_id", sa.Text(), nullable=False),
        sa.Column("plan_id", sa.Text(), nullable=True),
        sa.Column("direction", sa.Text(), nullable=True),
        sa.Column("plan_status", sa.Text(), nullable=False),
        sa.Column("entry_reference_price", sa.Numeric(28, 12), nullable=True),
        sa.Column("entry_low", sa.Numeric(28, 12), nullable=True),
        sa.Column("entry_high", sa.Numeric(28, 12), nullable=True),
        sa.Column("stop_loss_price", sa.Numeric(28, 12), nullable=True),
        sa.Column(
            "take_profit_targets",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("primary_rr", sa.Numeric(18, 8), nullable=True),
        sa.Column(
            "eligibility_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "plan_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("configuration_version", sa.Text(), nullable=False),
        sa.Column("analysis_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["analysis_snapshot_id"],
            ["analysis_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_run_id", name="uq_trade_plans_analysis_run_id"),
    )
    op.create_index(
        "uq_trade_plans_plan_id",
        "trade_plans",
        ["plan_id"],
        unique=True,
        postgresql_where=sa.text("plan_id IS NOT NULL"),
    )
    op.create_index(
        "ix_trade_plans_analysis_snapshot_id",
        "trade_plans",
        ["analysis_snapshot_id"],
        unique=False,
    )
    op.create_index(
        "ix_trade_plans_analysis_run_id",
        "trade_plans",
        ["analysis_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_trade_plans_analysis_run_id", table_name="trade_plans")
    op.drop_index("ix_trade_plans_analysis_snapshot_id", table_name="trade_plans")
    op.drop_index("uq_trade_plans_plan_id", table_name="trade_plans")
    op.drop_table("trade_plans")
    op.drop_index("ix_decisions_analysis_run_id", table_name="decisions")
    op.drop_index("ix_decisions_analysis_snapshot_id", table_name="decisions")
    op.drop_index("uq_decisions_decision_id", table_name="decisions")
    op.drop_table("decisions")
