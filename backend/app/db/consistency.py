"""Consistency status classifier for dual Decision/Trade-Plan saves (Phase 6.0.2)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


def _as_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        text = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


def _levels_close(a: Decimal | None, b: Decimal | None) -> bool:
    if a is None or b is None:
        return True  # only compared when both sides have a value
    if a == 0 and b == 0:
        return True
    diff = abs(a - b)
    if abs(a) < Decimal("1e-12") and abs(b) < Decimal("1e-12"):
        return diff <= Decimal("1e-12")
    rel = diff / max(abs(a), abs(b))
    return rel <= Decimal("1e-8") or diff <= Decimal("1e-12")


def _tp_lists_close(a: list[Any] | None, b: list[Any] | None) -> bool:
    if a is None or b is None:
        return True
    if len(a) != len(b):
        return False
    for left, right in zip(a, b, strict=True):
        da, db = _as_decimal(left), _as_decimal(right)
        if da is None or db is None:
            if left != right:
                return False
            continue
        if not _levels_close(da, db):
            return False
    return True


def _direction_compatible(decision: str | None, plan_direction: str | None) -> bool:
    if not decision or not plan_direction:
        return True
    d = decision.strip().upper()
    p = plan_direction.strip().upper()
    if d in {"WAIT", "NO TRADE", "NO_TRADE"}:
        return True
    if d == "LONG" and p in {"LONG", "BULLISH"}:
        return True
    if d == "SHORT" and p in {"SHORT", "BEARISH"}:
        return True
    return False


def classify_consistency(
    *,
    exchange: str | None,
    market_type: str | None,
    symbol: str | None,
    decision_payload: dict[str, Any] | None,
    trade_plan_payload: dict[str, Any] | None,
) -> str:
    """Return consistency_status per architecture §5."""
    has_decision = decision_payload is not None
    has_plan = trade_plan_payload is not None

    if not has_decision and not has_plan:
        return "INSUFFICIENT_PROVENANCE"
    if has_decision and not has_plan:
        return "DECISION_ONLY"
    if has_plan and not has_decision:
        return "PLAN_ONLY"

    assert decision_payload is not None and trade_plan_payload is not None

    if not exchange or not market_type or not symbol:
        return "INSUFFICIENT_PROVENANCE"

    d_ex = str(decision_payload.get("exchange") or exchange).strip().lower()
    p_ex = str(trade_plan_payload.get("exchange") or exchange).strip().lower()
    d_mt = str(decision_payload.get("market_type") or market_type).strip().lower()
    p_mt = str(trade_plan_payload.get("market_type") or market_type).strip().lower()
    d_sym = str(decision_payload.get("symbol") or symbol).strip().upper()
    p_sym = str(trade_plan_payload.get("symbol") or symbol).strip().upper()
    if d_ex != p_ex or d_mt != p_mt or d_sym != p_sym:
        return "DUAL_FETCH_DIVERGED"

    d_ts = _as_dt(
        decision_payload.get("analysis_timestamp")
        or decision_payload.get("timestamp")
    )
    p_ts = _as_dt(
        trade_plan_payload.get("analysis_timestamp")
        or trade_plan_payload.get("timestamp")
    )
    if d_ts is None or p_ts is None:
        return "INSUFFICIENT_PROVENANCE"
    if abs((d_ts - p_ts).total_seconds()) > 2.0:
        return "DUAL_FETCH_DIVERGED"

    d_entry = _as_decimal(decision_payload.get("entry_reference_price"))
    p_entry = _as_decimal(trade_plan_payload.get("entry_reference_price"))
    d_sl = _as_decimal(decision_payload.get("stop_loss_price"))
    p_sl = _as_decimal(
        trade_plan_payload.get("stop_loss_price")
        or trade_plan_payload.get("stop_loss")
    )
    d_tps = decision_payload.get("take_profit_prices") or decision_payload.get(
        "take_profits"
    )
    p_tps = (
        trade_plan_payload.get("take_profit_targets")
        or trade_plan_payload.get("take_profit_prices")
        or trade_plan_payload.get("take_profits")
    )
    if isinstance(d_tps, dict):
        d_tps = d_tps.get("prices") or list(d_tps.values())
    if isinstance(p_tps, dict):
        p_tps = p_tps.get("prices") or list(p_tps.values())

    if not _levels_close(d_entry, p_entry):
        return "DUAL_FETCH_DIVERGED"
    if not _levels_close(d_sl, p_sl):
        return "DUAL_FETCH_DIVERGED"
    if d_tps is not None and p_tps is not None and not _tp_lists_close(
        list(d_tps), list(p_tps)
    ):
        return "DUAL_FETCH_DIVERGED"

    if not _direction_compatible(
        str(decision_payload.get("decision") or ""),
        str(trade_plan_payload.get("direction") or ""),
    ):
        return "DUAL_FETCH_DIVERGED"

    return "ALIGNED"
