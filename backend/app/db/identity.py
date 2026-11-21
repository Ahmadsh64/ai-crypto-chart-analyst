"""Stable / deterministic identity helpers (Phase 6.0.2).

Does not change fill prices, quantities, or ambiguity policy math.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.json_codec import content_hash, decimal_to_str, jsonable


def _sha_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utc_iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def new_analysis_run_id() -> str:
    """Correlation id for one Analyze / save orchestration."""
    return "ar_" + uuid.uuid4().hex


def new_replay_session_id() -> str:
    """Allocate a new replay session business id (`rp_…`)."""
    return "rp_" + uuid.uuid4().hex[:16]


def stable_replay_session_id(
    *,
    exchange: str,
    market_type: str,
    symbol: str,
    start_time: datetime,
    end_time: datetime,
    salt: str = "",
) -> str:
    """Deterministic rebuild key for a logical replay window (optional salt)."""
    key = "|".join(
        [
            exchange.strip().lower(),
            market_type.strip().lower(),
            symbol.strip().upper(),
            _utc_iso(start_time),
            _utc_iso(end_time),
            salt,
        ]
    )
    return "rp_" + _sha_hex(key)[:16]


def deterministic_trade_id(
    *,
    replay_session_id: str,
    signal_key: str,
    decision_event_index: int,
    direction: str,
) -> str:
    """Architecture §6.2 — rebuild-safe simulated trade id."""
    material = (
        f"{replay_session_id}|{signal_key}|{decision_event_index}|{direction}"
    )
    return "st_" + _sha_hex(material)[:20]


def deterministic_event_id(
    *,
    replay_session_id: str,
    trade_id: str,
    event_type: str,
    candle_open_time: datetime | None,
    event_timestamp: datetime | None = None,
    tp_index: int | None = None,
) -> str:
    """Architecture §6.3 — rebuild-safe trade event id."""
    bar = candle_open_time if candle_open_time is not None else event_timestamp
    tp_key = -1 if tp_index is None else int(tp_index)
    material = (
        f"{replay_session_id}|{trade_id}|{event_type}|{_utc_iso(bar)}|{tp_key}"
    )
    return "se_" + _sha_hex(material)[:24]


def deterministic_execution_id(
    *,
    event_id: str,
    execution_role: str | None = None,
) -> str:
    """Architecture §7.3 — `ec_{event_id}` or `ec_{event_id}_{role}`."""
    if execution_role:
        return f"ec_{event_id}_{execution_role}"
    return f"ec_{event_id}"


def tp_index_key(tp_index: int | None) -> int:
    return -1 if tp_index is None else int(tp_index)


def event_payload_for_hash(
    *,
    price: Any = None,
    quantity: Any = None,
    remaining_quantity: Any = None,
    reason: str | None = None,
    ambiguity_policy_applied: str | None = None,
    event_timestamp: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Canonical subset hashed for trade_events.payload_hash conflict detection."""
    return {
        "ambiguity_policy_applied": ambiguity_policy_applied,
        "event_timestamp": _utc_iso(event_timestamp) if event_timestamp else None,
        "metadata": jsonable(metadata or {}),
        "price": decimal_to_str(price) if price is not None else None,
        "quantity": decimal_to_str(quantity) if quantity is not None else None,
        "reason": reason,
        "remaining_quantity": (
            decimal_to_str(remaining_quantity)
            if remaining_quantity is not None
            else None
        ),
    }


def compute_payload_hash(
    *,
    price: Any = None,
    quantity: Any = None,
    remaining_quantity: Any = None,
    reason: str | None = None,
    ambiguity_policy_applied: str | None = None,
    event_timestamp: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """SHA-256 of canonical event financial payload (architecture §6.4)."""
    return content_hash(
        event_payload_for_hash(
            price=price,
            quantity=quantity,
            remaining_quantity=remaining_quantity,
            reason=reason,
            ambiguity_policy_applied=ambiguity_policy_applied,
            event_timestamp=event_timestamp,
            metadata=metadata,
        )
    )


def resolve_event_conflict(
    *,
    existing_payload_hash: str,
    incoming_payload_hash: str,
) -> str:
    """
    Return 'idempotent' or raise via return code 'conflict'.

    Callers map:
      same hash → idempotent success
      different hash → integrity conflict (never overwrite)
    """
    if existing_payload_hash == incoming_payload_hash:
        return "idempotent"
    return "conflict"
