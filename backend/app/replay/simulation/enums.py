"""Trade simulation enums (Phase 5.2.2)."""

from __future__ import annotations

from typing import Literal

TradeDirection = Literal["LONG", "SHORT"]

TradeLifecycleStatus = Literal[
    "pending_entry",
    "open",
    "partially_closed",
    "closed_tp",
    "closed_sl",
    "closed_expired",
    "cancelled",
    "rejected",
    "ambiguous_execution",
]

EntryPricePolicy = Literal[
    "exact_reference_price",
    "zone_boundary",
    "zone_midpoint",
]

AmbiguityPolicy = Literal[
    "conservative_stop_first",
    "mark_ambiguous",
    "use_lower_timeframe_if_available",
]

SimulationEventType = Literal[
    "trade_pending",
    "trade_opened",
    "trade_partially_closed",
    "trade_closed",
    "trade_cancelled",
    "trade_rejected",
    "trade_ambiguous",
    "simulation_snapshot",
    "simulation_error",
]
