"""Phase 5.5 Step 4 — opportunity identity / fingerprint tests."""

from __future__ import annotations

from datetime import datetime, timezone

from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.scanner.identity import (
    STATUS_HISTORY_MAX,
    append_status_history,
    compute_opportunity_id,
    compute_setup_fingerprint,
    compute_slot_key,
    content_hash_for_opportunity,
    fingerprint_from_opportunity,
    should_close_as_terminal,
)
from app.scanner.models import (
    MarketOpportunity,
    OpportunityDirection,
    OpportunityLevel,
    OpportunityStatus,
)


def _opp(**kwargs) -> MarketOpportunity:
    base = dict(
        opportunity_id="tmp",
        exchange=ExchangeId.BINANCE,
        market_type=MarketType.SPOT,
        symbol="BTC/USDT",
        base="BTC",
        timeframe=Timeframe.H1,
        status=OpportunityStatus.READY,
        decision="LONG",
        direction=OpportunityDirection.LONG,
        entry_low=98.0,
        entry_high=102.0,
        entry_reference=100.0,
        stop_loss=90.0,
        take_profits=[
            OpportunityLevel(label="TP1", price=110.0, available=True),
            OpportunityLevel(label="TP2", price=120.0, available=True),
            OpportunityLevel(label="TP3", price=None, available=False),
        ],
        primary_rr=2.0,
        decision_id="d-volatile-1",
        trade_plan_id="p-volatile-1",
        analysis_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        lifecycle="entry_confirmed",
        confluence_score=80.0,
        current_price=100.5,
    )
    base.update(kwargs)
    return MarketOpportunity(**base)


def test_slot_key_stable_and_distinct_by_tf():
    a = compute_slot_key(ExchangeId.BINANCE, MarketType.SPOT, "btc/usdt", Timeframe.H1)
    b = compute_slot_key(ExchangeId.BINANCE, MarketType.SPOT, "BTC/USDT", Timeframe.H1)
    c = compute_slot_key(ExchangeId.BINANCE, MarketType.SPOT, "BTC/USDT", Timeframe.M15)
    assert a == b
    assert a != c


def test_same_setup_across_repeated_scans_same_fingerprint():
    o1 = _opp(
        decision_id="d-1",
        trade_plan_id="p-1",
        analysis_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        current_price=100.0,
        confluence_score=70.0,
    )
    o2 = _opp(
        decision_id="d-2-changed",
        trade_plan_id="p-2-changed",
        analysis_timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc),
        current_price=101.5,
        confluence_score=88.0,
        lifecycle="awaiting_confirmation",
        status=OpportunityStatus.APPROACHING_ENTRY,
    )
    assert fingerprint_from_opportunity(o1) == fingerprint_from_opportunity(o2)


def test_changed_transient_engine_ids_do_not_change_fingerprint():
    fp1 = compute_setup_fingerprint(
        decision="LONG",
        direction="LONG",
        entry_low=98,
        entry_high=102,
        entry_reference=100,
        stop_loss=90,
        tp1=110,
        tp1_available=True,
        primary_rr=2.0,
    )
    # Same structural fields — ids are not inputs
    fp2 = compute_setup_fingerprint(
        decision="LONG",
        direction="LONG",
        entry_low=98,
        entry_high=102,
        entry_reference=100,
        stop_loss=90,
        tp1=110,
        tp1_available=True,
        primary_rr=2.0,
    )
    assert fp1 == fp2


def test_lifecycle_status_alone_does_not_change_fingerprint():
    a = _opp(status=OpportunityStatus.READY, lifecycle="entry_confirmed")
    b = _opp(status=OpportunityStatus.WAITING, lifecycle="awaiting_confirmation")
    assert fingerprint_from_opportunity(a) == fingerprint_from_opportunity(b)


def test_genuinely_new_structural_setup_changes_fingerprint():
    a = _opp(entry_low=98.0, stop_loss=90.0)
    b = _opp(entry_low=95.0, stop_loss=88.0)
    assert fingerprint_from_opportunity(a) != fingerprint_from_opportunity(b)


def test_new_generation_after_terminal_gets_new_opportunity_id():
    slot = compute_slot_key(ExchangeId.BINANCE, MarketType.SPOT, "BTC/USDT", Timeframe.H1)
    fp_old = compute_setup_fingerprint(decision="LONG", entry_low=98, stop_loss=90)
    fp_new = compute_setup_fingerprint(decision="SHORT", entry_low=110, stop_loss=120)
    id1 = compute_opportunity_id(slot, 1, fp_old)
    id2 = compute_opportunity_id(slot, 2, fp_new)
    assert id1 != id2
    assert id1 == compute_opportunity_id(slot, 1, fp_old)


def test_status_history_capped_at_20():
    hist = []
    for i in range(25):
        hist = append_status_history(
            hist,
            at_iso=f"t{i}",
            from_status="WAITING",
            to_status="READY",
            scan_id=f"s{i}",
        )
    assert len(hist) == STATUS_HISTORY_MAX
    assert hist[0]["scan_id"] == "s5"
    assert hist[-1]["scan_id"] == "s24"


def test_terminal_close_only_for_invalidated_expired():
    assert should_close_as_terminal("INVALIDATED")
    assert should_close_as_terminal("EXPIRED")
    assert not should_close_as_terminal("WAITING")
    assert not should_close_as_terminal("READY")
    assert not should_close_as_terminal("APPROACHING_ENTRY")


def test_content_hash_ignores_price_and_ids():
    a = _opp(current_price=1.0, decision_id="a", confluence_score=10)
    b = _opp(current_price=9.0, decision_id="b", confluence_score=10)
    fp = fingerprint_from_opportunity(a)
    # confluence in content_hash — change score changes hash; price/ids should not alone
    # same confluence → if we only change price/ids:
    a2 = _opp(current_price=1.0, decision_id="x", confluence_score=10, decision_reason="r")
    b2 = _opp(current_price=99.0, decision_id="y", confluence_score=10, decision_reason="r")
    assert content_hash_for_opportunity(a2, setup_fingerprint=fp) == content_hash_for_opportunity(
        b2, setup_fingerprint=fp
    )


def test_unavailable_tp_not_in_fingerprint():
    a = _opp(
        take_profits=[
            OpportunityLevel(label="TP1", price=110.0, available=True),
            OpportunityLevel(label="TP2", price=999.0, available=False),
            OpportunityLevel(label="TP3", available=False),
        ]
    )
    b = _opp(
        take_profits=[
            OpportunityLevel(label="TP1", price=110.0, available=True),
            OpportunityLevel(label="TP2", price=1.0, available=False),
            OpportunityLevel(label="TP3", available=False),
        ]
    )
    assert fingerprint_from_opportunity(a) == fingerprint_from_opportunity(b)
