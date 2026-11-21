"""Trade lifecycle helpers (Phase 5.2.2 + Phase 6.0.2 identity).

Deterministic trade/event IDs are rebuild-safe. Fill prices, quantities, and
ambiguity policy semantics are unchanged.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.db.identity import (
    compute_payload_hash,
    deterministic_event_id,
    deterministic_trade_id,
)
from app.replay.simulation.enums import SimulationEventType
from app.replay.simulation.models import SimulationExecutionEvent, SimulatedTrade


def new_event_id(
    *,
    replay_session_id: str | None = None,
    trade_id: str | None = None,
    event_type: str | None = None,
    candle_open_time: datetime | None = None,
    event_timestamp: datetime | None = None,
    tp_index: int | None = None,
) -> str:
    """Prefer deterministic event id when rebuild context is provided."""
    if replay_session_id and trade_id and event_type:
        return deterministic_event_id(
            replay_session_id=replay_session_id,
            trade_id=trade_id,
            event_type=event_type,
            candle_open_time=candle_open_time,
            event_timestamp=event_timestamp,
            tp_index=tp_index,
        )
    return "se_" + uuid.uuid4().hex[:12]


def new_trade_id(
    *,
    replay_session_id: str | None = None,
    signal_key: str | None = None,
    decision_event_index: int | None = None,
    direction: str | None = None,
) -> str:
    """Prefer deterministic trade id when rebuild context is provided."""
    if (
        replay_session_id is not None
        and signal_key is not None
        and decision_event_index is not None
        and direction is not None
    ):
        return deterministic_trade_id(
            replay_session_id=replay_session_id,
            signal_key=signal_key,
            decision_event_index=decision_event_index,
            direction=str(direction),
        )
    return "st_" + uuid.uuid4().hex[:16]


def append_event(
    trade: SimulatedTrade,
    *,
    event_type: SimulationEventType,
    timestamp: datetime,
    price: float | None = None,
    quantity: float | None = None,
    tp_index: int | None = None,
    reason: str | None = None,
    ambiguity_policy_applied: str | None = None,
    candle_open_time: datetime | None = None,
    metadata: dict | None = None,
) -> SimulationExecutionEvent:
    event_id = new_event_id(
        replay_session_id=trade.replay_session_id,
        trade_id=trade.trade_id,
        event_type=str(event_type),
        candle_open_time=candle_open_time,
        event_timestamp=timestamp,
        tp_index=tp_index,
    )
    # payload_hash computed for future persistence conflict detection (6.0.5)
    _ = compute_payload_hash(
        price=price,
        quantity=quantity,
        remaining_quantity=trade.remaining_quantity,
        reason=reason,
        ambiguity_policy_applied=ambiguity_policy_applied,
        event_timestamp=timestamp,
        metadata=metadata or {},
    )
    ev = SimulationExecutionEvent(
        event_id=event_id,
        event_type=event_type,
        timestamp=timestamp,
        price=price,
        quantity=quantity,
        remaining_quantity=trade.remaining_quantity,
        tp_index=tp_index,
        reason=reason,
        ambiguity_policy_applied=ambiguity_policy_applied,
        candle_open_time=candle_open_time,
        metadata=metadata or {},
    )
    trade.execution_events.append(ev)
    trade.updated_at = datetime.now(timezone.utc)
    return ev
