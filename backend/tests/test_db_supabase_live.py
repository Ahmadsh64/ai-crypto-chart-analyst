"""
LIVE Supabase connectivity & migration tests (Phase 6.0.2).

These tests run ONLY when real credentials are configured:

  PERSISTENCE_ENABLED=true
  DATABASE_URL or SUPABASE_DB_URL pointing at Supabase/PostgreSQL

They are distinct from local/mocked unit tests in test_db_phase_6_0_2.py.

If credentials are absent → tests are SKIPPED (NOT VERIFIED), never failed.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.db.identity import new_analysis_run_id
from app.db.repositories.analysis import persist_analysis_bundle
from app.db.session import close_db, get_engine, init_db, ping_database


def _live_settings() -> Settings | None:
    """Return settings only when the operator explicitly enabled live persistence."""
    # Bypass lru_cache so test env vars are visible
    get_settings.cache_clear()
    s = Settings()
    if not s.persistence_enabled:
        return None
    url = s.effective_database_url
    # Refuse obvious local defaults when claiming "live Supabase"
    if "localhost" in url or "127.0.0.1" in url:
        # Still allow local Postgres as a live integration target when flagged
        if os.environ.get("ALLOW_LOCAL_DB_LIVE_TEST", "").lower() not in {
            "1",
            "true",
            "yes",
        }:
            return None
    return s


pytestmark = pytest.mark.skipif(
    _live_settings() is None,
    reason=(
        "LIVE Supabase/Postgres NOT VERIFIED — set PERSISTENCE_ENABLED=true "
        "and DATABASE_URL/SUPABASE_DB_URL (use ALLOW_LOCAL_DB_LIVE_TEST=true "
        "for localhost)."
    ),
)


@pytest.fixture
async def live_db():
    settings = _live_settings()
    assert settings is not None
    get_settings.cache_clear()
    ok = await init_db(settings)
    assert ok, "Live DB init failed"
    yield settings
    await close_db()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_live_ping(live_db):
    status, detail = await ping_database(live_db)
    assert status == "ok", detail
    assert "reachable" in detail.lower() or "postgresql" in detail.lower()


@pytest.mark.asyncio
async def test_live_select_one(live_db):
    engine = get_engine(live_db)
    assert engine is not None
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar_one() == 1


@pytest.mark.asyncio
async def test_live_migrations_applied(live_db):
    """Requires `alembic upgrade head` already run against the target DB."""
    engine = get_engine(live_db)
    assert engine is not None
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' "
                "AND tablename IN ("
                "'analysis_sessions','analysis_snapshots','decisions','trade_plans'"
                ")"
            )
        )
        names = {r[0] for r in rows}
    missing = {
        "analysis_sessions",
        "analysis_snapshots",
        "decisions",
        "trade_plans",
    } - names
    assert not missing, (
        f"Missing tables {missing}. Run: cd backend && alembic upgrade head"
    )


@pytest.mark.asyncio
async def test_live_atomic_persist_idempotent(live_db):
    engine = get_engine(live_db)
    assert engine is not None
    # Skip if migrations not applied
    async with engine.connect() as conn:
        exists = await conn.execute(
            text(
                "SELECT to_regclass('public.analysis_snapshots') IS NOT NULL"
            )
        )
        if not exists.scalar_one():
            pytest.skip("Migrations not applied — run alembic upgrade head")

    run_id = new_analysis_run_id()
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    decision = {
        "decision_id": f"dec_{run_id}",
        "decision": "NO TRADE",
        "decision_reason": "live test",
        "exchange": "binance",
        "market_type": "spot",
        "symbol": "BTC/USDT",
        "analysis_timestamp": ts,
        "entry_reference_price": None,
        "stop_loss_price": None,
        "configuration_version": "test-6.0.2",
        "bullish_score": Decimal("1.5"),
        "bearish_score": Decimal("2.5"),
    }
    plan = {
        "plan_id": f"plan_{run_id}",
        "direction": None,
        "plan_status": "blocked",
        "exchange": "binance",
        "market_type": "spot",
        "symbol": "BTC/USDT",
        "analysis_timestamp": ts,
        "eligibility": {"ok": False},
        "configuration_version": "test-6.0.2",
    }
    r1 = await persist_analysis_bundle(
        exchange="binance",
        market_type="spot",
        symbol="BTC/USDT",
        decision=decision,
        trade_plan=plan,
        analysis_run_id=run_id,
    )
    assert r1.created is True
    assert r1.consistency_status in {
        "ALIGNED",
        "DUAL_FETCH_DIVERGED",
        "DECISION_ONLY",
        "PLAN_ONLY",
        "INSUFFICIENT_PROVENANCE",
    }
    r2 = await persist_analysis_bundle(
        exchange="binance",
        market_type="spot",
        symbol="BTC/USDT",
        decision=decision,
        trade_plan=plan,
        analysis_run_id=run_id,
    )
    assert r2.idempotent is True
    assert r2.snapshot_id == r1.snapshot_id
