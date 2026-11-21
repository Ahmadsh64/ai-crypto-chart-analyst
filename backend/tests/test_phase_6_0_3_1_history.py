"""Phase 6.0.3.1 — read-only Analysis History API tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.repositories.history import AnalysisHistoryRepository
from app.main import create_app


def _snap(
    *,
    run_id: str,
    symbol: str = "BTC/USDT",
    exchange: str = "binance",
    market_type: str = "spot",
    timeframe: str = "1h",
    decision: str = "LONG",
    consistency: str = "ALIGNED",
    ts: datetime | None = None,
    entry: str | None = "100",
    sl: str | None = "90",
    tps: list | None = None,
) -> SimpleNamespace:
    sid = uuid4()
    return SimpleNamespace(
        id=sid,
        analysis_run_id=run_id,
        analysis_session_id=uuid4(),
        snapshot_kind="live_analyze",
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        timeframe=timeframe,
        analysis_timestamp=ts or datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
        decision_analysis_timestamp=ts or datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
        trade_plan_analysis_timestamp=ts or datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
        consistency_status=consistency,
        decision=decision,
        decision_id="d1",
        plan_id="p1",
        configuration_versions={"decision": "decision-v1"},
        snapshot_schema_version="analysis-snapshot-db-v1",
        data_freshness="fresh",
        entry_reference_price=Decimal(entry) if entry else None,
        entry_low=Decimal("99") if entry else None,
        entry_high=Decimal("101") if entry else None,
        stop_loss_price=Decimal(sl) if sl else None,
        take_profit_prices=tps if tps is not None else [Decimal("110"), Decimal("120")],
        primary_rr=Decimal("2.0"),
        confluence_bullish=Decimal("3.0"),
        confluence_bearish=Decimal("1.0"),
        snapshot_payload={
            "decision": {"decision": decision, "raw": True},
            "trade_plan": {"plan_id": "p1"},
        },
        content_hash="hash1",
        created_at=datetime(2024, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
        session=SimpleNamespace(
            id=uuid4(),
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
            primary_timeframe=timeframe,
            status="active",
            source="live_analyze",
            created_at=datetime(2024, 6, 1, 11, 0, tzinfo=timezone.utc),
            updated_at=datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
        ),
        decision_row=SimpleNamespace(
            decision=decision,
            decision_reason="unit",
            lifecycle="blocked",
            direction=None,
            decision_id="d1",
            bullish_score=Decimal("3.0"),
            bearish_score=Decimal("1.0"),
            evidence_payload=["e1"],
            conflicts_payload=[],
            blocking_conditions=[],
            configuration_version="decision-v1",
            analysis_timestamp=ts or datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
        ),
        trade_plan_row=SimpleNamespace(
            plan_payload={"plan_id": "p1", "source": "trade_plan"}
        ),
    )


@pytest.fixture
def client():
    return TestClient(create_app())


def test_list_returns_503_when_persistence_disabled(client: TestClient):
    with patch("app.api.routes.history.is_persistence_active", return_value=False):
        res = client.get("/api/v1/history/analyses")
    assert res.status_code == 503
    body = res.json()
    assert body["detail"]["code"] == "PERSISTENCE_DISABLED"
    assert "items" not in body


def test_list_returns_503_when_factory_missing(client: TestClient):
    with (
        patch("app.api.routes.history.is_persistence_active", return_value=True),
        patch("app.api.routes.history.get_async_session_factory", return_value=None),
    ):
        res = client.get("/api/v1/history/analyses")
    assert res.status_code == 503
    assert res.json()["detail"]["code"] == "DATABASE_UNAVAILABLE"


def test_list_pagination_and_stable_ordering(client: TestClient):
    t0 = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    rows = [
        _snap(run_id="ar_a", ts=t0 + timedelta(hours=2), decision="LONG"),
        _snap(run_id="ar_b", ts=t0 + timedelta(hours=1), decision="WAIT"),
    ]
    session = AsyncMock()
    session.close = AsyncMock()
    factory = MagicMock(return_value=session)

    async def list_analyses(**kwargs):
        assert kwargs["limit"] == 1
        assert kwargs["offset"] == 0
        return rows[:1], 2

    with (
        patch("app.api.routes.history.is_persistence_active", return_value=True),
        patch("app.api.routes.history.get_async_session_factory", return_value=factory),
        patch.object(AnalysisHistoryRepository, "list_analyses", side_effect=list_analyses),
    ):
        res = client.get("/api/v1/history/analyses?limit=1&offset=0")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert data["limit"] == 1
    assert data["offset"] == 0
    assert len(data["items"]) == 1
    assert data["items"][0]["analysis_run_id"] == "ar_a"
    assert data["items"][0]["decision"] == "LONG"


def test_list_filters_forwarded(client: TestClient):
    session = AsyncMock()
    session.close = AsyncMock()
    factory = MagicMock(return_value=session)
    captured: dict = {}

    async def list_analyses(**kwargs):
        captured.update(kwargs)
        return [], 0

    with (
        patch("app.api.routes.history.is_persistence_active", return_value=True),
        patch("app.api.routes.history.get_async_session_factory", return_value=factory),
        patch.object(AnalysisHistoryRepository, "list_analyses", side_effect=list_analyses),
    ):
        res = client.get(
            "/api/v1/history/analyses"
            "?exchange=binance&market_type=spot&symbol=btcusdt"
            "&timeframe=1h&decision=NO%20TRADE"
            "&from=2024-01-01T00:00:00Z&to=2024-12-31T23:59:59Z"
        )
    assert res.status_code == 200
    assert captured["exchange"] == "binance"
    assert captured["market_type"] == "spot"
    assert captured["symbol"] == "BTC/USDT"
    assert captured["timeframe"] == "1h"
    assert captured["decision"] == "NO TRADE"
    assert captured["from_ts"] is not None
    assert captured["to_ts"] is not None


def test_list_rejects_invalid_decision(client: TestClient):
    with patch("app.api.routes.history.is_persistence_active", return_value=True):
        res = client.get("/api/v1/history/analyses?decision=BUY")
    assert res.status_code == 422


def test_detail_by_run(client: TestClient):
    row = _snap(run_id="ar_detail", consistency="DUAL_FETCH_DIVERGED")
    # Preserve diverged payloads honestly
    row.snapshot_payload = {
        "decision": {"decision": "LONG", "v": 1},
        "trade_plan": {"decision": "WAIT", "v": 2},
    }
    session = AsyncMock()
    session.close = AsyncMock()
    factory = MagicMock(return_value=session)

    with (
        patch("app.api.routes.history.is_persistence_active", return_value=True),
        patch("app.api.routes.history.get_async_session_factory", return_value=factory),
        patch.object(
            AnalysisHistoryRepository,
            "get_by_run_id",
            new=AsyncMock(return_value=row),
        ),
    ):
        res = client.get("/api/v1/history/analyses/by-run/ar_detail")
    assert res.status_code == 200
    data = res.json()
    assert data["analysis_run_id"] == "ar_detail"
    assert data["consistency_status"] == "DUAL_FETCH_DIVERGED"
    assert data["snapshot_payload"]["decision"]["decision"] == "LONG"
    assert data["snapshot_payload"]["trade_plan"]["decision"] == "WAIT"
    assert data["entry_reference_price"] == "100"
    assert data["take_profit_prices"] == ["110", "120"]
    assert "not exchange fills" in data["levels_note"].lower()
    assert data["decision_extract"]["decision"] == "LONG"
    assert data["trade_plan_extract"]["plan_id"] == "p1"


def test_detail_alias_path(client: TestClient):
    row = _snap(run_id="ar_alias")
    session = AsyncMock()
    session.close = AsyncMock()
    factory = MagicMock(return_value=session)

    with (
        patch("app.api.routes.history.is_persistence_active", return_value=True),
        patch("app.api.routes.history.get_async_session_factory", return_value=factory),
        patch.object(
            AnalysisHistoryRepository,
            "get_by_run_id",
            new=AsyncMock(return_value=row),
        ),
        patch.object(
            AnalysisHistoryRepository,
            "get_by_snapshot_id",
            new=AsyncMock(return_value=None),
        ),
    ):
        res = client.get("/api/v1/history/analyses/ar_alias")
    assert res.status_code == 200
    assert res.json()["analysis_run_id"] == "ar_alias"


def test_detail_missing_404(client: TestClient):
    session = AsyncMock()
    session.close = AsyncMock()
    factory = MagicMock(return_value=session)

    with (
        patch("app.api.routes.history.is_persistence_active", return_value=True),
        patch("app.api.routes.history.get_async_session_factory", return_value=factory),
        patch.object(
            AnalysisHistoryRepository,
            "get_by_run_id",
            new=AsyncMock(return_value=None),
        ),
    ):
        res = client.get("/api/v1/history/analyses/by-run/missing")
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "ANALYSIS_NOT_FOUND"


def test_detail_503_when_disabled(client: TestClient):
    with patch("app.api.routes.history.is_persistence_active", return_value=False):
        res = client.get("/api/v1/history/analyses/by-run/ar_x")
    assert res.status_code == 503


def test_to_list_item_and_detail_serializers():
    row = _snap(run_id="ar_ser", consistency="DECISION_ONLY")
    item = AnalysisHistoryRepository.to_list_item(row)
    assert item["analysis_run_id"] == "ar_ser"
    assert item["snapshot_id"] == str(row.id)
    assert item["entry_reference_price"] == "100"
    detail = AnalysisHistoryRepository.to_detail(row)
    assert detail["session"]["symbol"] == "BTC/USDT"
    assert detail["consistency_status"] == "DECISION_ONLY"
    # Prefer raw_decision from snapshot_payload when present.
    assert detail["decision_extract"]["decision"] == "LONG"
    assert detail["trade_plan_extract"]["plan_id"] == "p1"


def test_history_routes_do_not_import_live_engines():
    """Smoke: history module must not depend on decision/trade_plan services."""
    import app.api.routes.history as history_mod

    src = open(history_mod.__file__, encoding="utf-8").read()
    assert "decision_engine" not in src
    assert "trade_plan_service" not in src
    assert "compute_decision" not in src
    assert "persist_live_analyze" not in src
    assert "get_candles" not in src
