"""Trade lifecycle helpers (Phase 5.2.2)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.replay.simulation.enums import SimulationEventType
from app.replay.simulation.models import SimulationExecutionEvent, SimulatedTrade


def new_event_id() -> str:
    return "se_" + uuid.uuid4().hex[:12]


def new_trade_id() -> str:
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
    ev = SimulationExecutionEvent(
        event_id=new_event_id(),
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
