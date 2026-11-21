"""Phase 6.0.2 unit tests — identity, JSON codec, consistency (no live DB)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.db.consistency import classify_consistency
from app.db.exceptions import IdempotencyConflictError
from app.db.identity import (
    compute_payload_hash,
    deterministic_event_id,
    deterministic_execution_id,
    deterministic_trade_id,
    new_analysis_run_id,
    new_replay_session_id,
    resolve_event_conflict,
    stable_replay_session_id,
)
from app.db.json_codec import canonical_json_bytes, content_hash, decimal_to_str, jsonable
from app.db.session import is_persistence_active, ping_database
from app.core.config import Settings


def test_persistence_disabled_by_default():
    s = Settings(persistence_enabled=False)
    assert is_persistence_active(s) is False


@pytest.mark.asyncio
async def test_ping_database_when_disabled():
    s = Settings(persistence_enabled=False)
    status, detail = await ping_database(s)
    assert status == "ok"
    assert "disabled" in detail.lower()


def test_analysis_run_id_format():
    rid = new_analysis_run_id()
    assert rid.startswith("ar_")
    assert len(rid) > 10


def test_replay_session_ids():
    a = new_replay_session_id()
    b = new_replay_session_id()
    assert a.startswith("rp_")
    assert a != b
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)
    s1 = stable_replay_session_id(
        exchange="binance",
        market_type="spot",
        symbol="BTC/USDT",
        start_time=start,
        end_time=end,
    )
    s2 = stable_replay_session_id(
        exchange="binance",
        market_type="spot",
        symbol="BTC/USDT",
        start_time=start,
        end_time=end,
    )
    assert s1 == s2
    assert s1.startswith("rp_")


def test_deterministic_trade_and_event_ids():
    tid = deterministic_trade_id(
        replay_session_id="rp_abc",
        signal_key="sig|1",
        decision_event_index=3,
        direction="LONG",
    )
    assert tid.startswith("st_")
    assert tid == deterministic_trade_id(
        replay_session_id="rp_abc",
        signal_key="sig|1",
        decision_event_index=3,
        direction="LONG",
    )
    ts = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    eid = deterministic_event_id(
        replay_session_id="rp_abc",
        trade_id=tid,
        event_type="trade_opened",
        candle_open_time=ts,
        tp_index=None,
    )
    assert eid.startswith("se_")
    assert eid == deterministic_event_id(
        replay_session_id="rp_abc",
        trade_id=tid,
        event_type="trade_opened",
        candle_open_time=ts,
        tp_index=None,
    )
    assert deterministic_execution_id(event_id=eid) == f"ec_{eid}"
    assert (
        deterministic_execution_id(event_id=eid, execution_role="exit")
        == f"ec_{eid}_exit"
    )


def test_payload_hash_conflict_detection():
    ts = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    h1 = compute_payload_hash(price="100.5", quantity="1", event_timestamp=ts)
    h2 = compute_payload_hash(price="100.5", quantity="1", event_timestamp=ts)
    h3 = compute_payload_hash(price="100.6", quantity="1", event_timestamp=ts)
    assert h1 == h2
    assert resolve_event_conflict(
        existing_payload_hash=h1, incoming_payload_hash=h2
    ) == "idempotent"
    assert resolve_event_conflict(
        existing_payload_hash=h1, incoming_payload_hash=h3
    ) == "conflict"


def test_decimal_json_codec_no_floats():
    payload = {
        "price": Decimal("101.250000"),
        "nested": {"qty": Decimal("0.001")},
        "list": [Decimal("1"), 2],
        "ts": datetime(2024, 1, 1, tzinfo=timezone.utc),
    }
    encoded = jsonable(payload)
    assert encoded["price"] == "101.25"
    assert encoded["nested"]["qty"] == "0.001"
    assert isinstance(encoded["list"][0], str)
    assert encoded["ts"].endswith("Z")
    # Key order independence
    a = content_hash({"b": "1", "a": "2"})
    b = content_hash({"a": "2", "b": "1"})
    assert a == b
    raw = canonical_json_bytes({"z": Decimal("1.0"), "a": Decimal("2")})
    assert b'"a":"2"' in raw
    assert decimal_to_str(Decimal("1E-3")) == "0.001"


def test_consistency_aligned_and_diverged():
    ts = "2024-06-01T12:00:00Z"
    decision = {
        "exchange": "binance",
        "market_type": "spot",
        "symbol": "BTC/USDT",
        "decision": "LONG",
        "analysis_timestamp": ts,
        "entry_reference_price": "100",
        "stop_loss_price": "90",
        "take_profit_prices": ["110", "120"],
    }
    plan = {
        "exchange": "binance",
        "market_type": "spot",
        "symbol": "BTC/USDT",
        "direction": "LONG",
        "analysis_timestamp": ts,
        "entry_reference_price": "100",
        "stop_loss_price": "90",
        "take_profit_targets": ["110", "120"],
    }
    assert (
        classify_consistency(
            exchange="binance",
            market_type="spot",
            symbol="BTC/USDT",
            decision_payload=decision,
            trade_plan_payload=plan,
        )
        == "ALIGNED"
    )
    plan_div = {**plan, "stop_loss_price": "85"}
    assert (
        classify_consistency(
            exchange="binance",
            market_type="spot",
            symbol="BTC/USDT",
            decision_payload=decision,
            trade_plan_payload=plan_div,
        )
        == "DUAL_FETCH_DIVERGED"
    )
    assert (
        classify_consistency(
            exchange="binance",
            market_type="spot",
            symbol="BTC/USDT",
            decision_payload=decision,
            trade_plan_payload=None,
        )
        == "DECISION_ONLY"
    )


def test_lifecycle_uses_deterministic_ids():
    from app.replay.simulation.lifecycle import append_event, new_trade_id
    from app.replay.simulation.models import SimulatedTrade

    tid = new_trade_id(
        replay_session_id="rp_x",
        signal_key="k",
        decision_event_index=1,
        direction="LONG",
    )
    assert tid.startswith("st_")
    now = datetime.now(timezone.utc)
    trade = SimulatedTrade(
        trade_id=tid,
        signal_key="k",
        replay_session_id="rp_x",
        exchange="binance",
        symbol="BTC/USDT",
        market_type="spot",
        direction="LONG",
        decision="LONG",
        decision_timestamp=now,
        decision_event_index=1,
        lifecycle_status="pending_entry",
        initial_stop_loss=90.0,
        current_stop_loss=90.0,
        original_quantity=1.0,
        remaining_quantity=1.0,
        config_version="t",
        created_at=now,
        updated_at=now,
    )
    candle = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    e1 = append_event(
        trade,
        event_type="trade_pending",
        timestamp=candle,
        candle_open_time=candle,
        price=100.0,
        quantity=1.0,
    )
    # Clear and re-append with same logical key → same event_id
    trade.execution_events.clear()
    e2 = append_event(
        trade,
        event_type="trade_pending",
        timestamp=candle,
        candle_open_time=candle,
        price=100.0,
        quantity=1.0,
    )
    assert e1.event_id == e2.event_id
    assert e1.event_id.startswith("se_")


def test_idempotency_conflict_error_code():
    err = IdempotencyConflictError(
        "mismatch",
        identity_key="ar_1",
        existing_hash="aaa",
        incoming_hash="bbb",
    )
    assert err.code == "IDEMPOTENCY_CONFLICT"
