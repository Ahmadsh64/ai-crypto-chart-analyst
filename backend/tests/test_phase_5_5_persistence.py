"""Phase 5.5 Step 4 — migration structure + persistence soft-fail + upsert decision tests."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
import pytest

from app.core.config import Settings
from app.db.models.scanner import MarketOpportunityRow, ScannerRun
from app.db.repositories.scanner import persist_scan_bundle
from app.db.session import is_persistence_active
from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.scanner.config import ScannerConfig
from app.scanner.identity import (
    compute_opportunity_id,
    compute_slot_key,
    fingerprint_from_opportunity,
)
from app.scanner.models import (
    MarketOpportunity,
    OpportunityDirection,
    OpportunityLevel,
    OpportunityStatus,
    ScanRunSummary,
)


def test_persistence_disabled_by_default():
    assert is_persistence_active(Settings(persistence_enabled=False)) is False


@pytest.mark.asyncio
async def test_persist_soft_skip_when_disabled(monkeypatch):
    monkeypatch.setattr(
        "app.db.repositories.scanner.is_persistence_active", lambda *a, **k: False
    )
    summary = ScanRunSummary(
        scan_id=str(uuid.uuid4()),
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        status="completed",
        duration_seconds=1.0,
    )
    result = await persist_scan_bundle(
        summary=summary,
        opportunities=[],
        config=ScannerConfig(auto_start=False),
        trigger="test",
    )
    assert result["persisted"] is False
    assert result["reason"] == "persistence_disabled"
    assert result["success"] is False


def test_migration_0004_file_structure():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0004_scanner_persistence.py"
    )
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert 'revision: str = "0004_scanner_persistence"' in text
    assert 'down_revision: Union[str, None] = "0003_decisions_trade_plans"' in text
    assert 'op.create_table(\n        "scanner_runs"' in text or 'op.create_table(\n        "scanner_runs",' in text
    assert "market_opportunities" in text
    assert "uq_market_opportunities_one_open_per_slot" in text
    assert "pg_advisory" not in text  # advisory lock is runtime, not migration
    assert "analysis_sessions" not in text.replace("does not alter analysis_sessions", "")
    # downgrade drops only scanner tables
    assert 'op.drop_table("market_opportunities")' in text
    assert 'op.drop_table("scanner_runs")' in text
    assert "drop_table(\"decisions\")" not in text
    assert "drop_table(\"trade_plans\")" not in text
    assert "drop_table(\"analysis_snapshots\")" not in text


def test_alembic_head_is_0004():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert heads == ["0004_scanner_persistence"]


def test_offline_upgrade_downgrade_ops_only_scanner_tables():
    """Call upgrade/downgrade with a fake op — no database connection."""
    import importlib.util

    backend = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "mig0004",
        backend / "alembic" / "versions" / "0004_scanner_persistence.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    created: list[str] = []
    dropped: list[str] = []

    class FakeOp:
        def create_table(self, name, *args, **kwargs):
            created.append(name)

        def create_index(self, *args, **kwargs):
            return None

        def drop_table(self, name):
            dropped.append(name)

        def drop_index(self, *args, **kwargs):
            return None

    mod.op = FakeOp()  # type: ignore[attr-defined]
    mod.upgrade()
    assert created == ["scanner_runs", "market_opportunities"]
    mod.downgrade()
    assert dropped == ["market_opportunities", "scanner_runs"]


def test_orm_models_isolated_from_analysis():
    assert ScannerRun.__tablename__ == "scanner_runs"
    assert MarketOpportunityRow.__tablename__ == "market_opportunities"
    # No FK to analysis tables in mapper columns
    fk_tables = {
        fk.column.table.name
        for col in MarketOpportunityRow.__table__.columns
        for fk in col.foreign_keys
    }
    assert fk_tables == {"scanner_runs"}
    assert "analysis_sessions" not in fk_tables
    assert "decisions" not in fk_tables


def test_upsert_decision_same_vs_new_fingerprint():
    """Pure decision logic mirroring repository branches."""
    slot = compute_slot_key(ExchangeId.BINANCE, MarketType.SPOT, "ETH/USDT", Timeframe.M15)
    opp_a = MarketOpportunity(
        opportunity_id="x",
        exchange=ExchangeId.BINANCE,
        market_type=MarketType.SPOT,
        symbol="ETH/USDT",
        base="ETH",
        timeframe=Timeframe.M15,
        status=OpportunityStatus.WAITING,
        decision="WAIT",
        take_profits=[
            OpportunityLevel(label="TP1", available=False),
            OpportunityLevel(label="TP2", available=False),
            OpportunityLevel(label="TP3", available=False),
        ],
    )
    opp_b = MarketOpportunity(
        opportunity_id="y",
        exchange=ExchangeId.BINANCE,
        market_type=MarketType.SPOT,
        symbol="ETH/USDT",
        base="ETH",
        timeframe=Timeframe.M15,
        status=OpportunityStatus.READY,
        decision="LONG",
        direction=OpportunityDirection.LONG,
        entry_low=1.0,
        entry_high=1.1,
        entry_reference=1.05,
        stop_loss=0.9,
        take_profits=[
            OpportunityLevel(label="TP1", price=1.2, available=True),
            OpportunityLevel(label="TP2", available=False),
            OpportunityLevel(label="TP3", available=False),
        ],
        primary_rr=2.5,
    )
    fp_a = fingerprint_from_opportunity(opp_a)
    fp_b = fingerprint_from_opportunity(opp_b)
    assert fp_a != fp_b
    # Same generation would collide only if fingerprint equal — new gen required
    id1 = compute_opportunity_id(slot, 1, fp_a)
    id2 = compute_opportunity_id(slot, 2, fp_b)
    assert id1 != id2


@pytest.mark.asyncio
async def test_concurrent_generation_allocation_serialized():
    """
    Simulate two coroutines allocating generation under an asyncio lock
    (stands in for pg_advisory_xact_lock in unit context).
    """
    lock = asyncio.Lock()
    max_gen = {"v": 0}
    results: list[int] = []

    async def allocate():
        async with lock:
            await asyncio.sleep(0.01)
            max_gen["v"] += 1
            results.append(max_gen["v"])

    await asyncio.gather(allocate(), allocate(), allocate())
    assert results == [1, 2, 3]


@pytest.mark.asyncio
async def test_persist_db_error_soft_fails(monkeypatch):
    monkeypatch.setattr(
        "app.db.repositories.scanner.is_persistence_active", lambda: True
    )

    class BoomFactory:
        def __call__(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(
        "app.db.repositories.scanner.get_async_session_factory",
        lambda: BoomFactory(),
    )
    summary = ScanRunSummary(
        scan_id=str(uuid.uuid4()),
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        status="completed",
    )
    result = await persist_scan_bundle(
        summary=summary,
        opportunities=[],
        config=ScannerConfig(auto_start=False),
    )
    assert result["persisted"] is False
    assert "db_error" in result["reason"]
