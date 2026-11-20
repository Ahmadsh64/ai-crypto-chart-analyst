"""Performance analytics enums (Phase 5.2.4)."""

from __future__ import annotations

from typing import Literal

AnalyticsTradeClass = Literal[
    "closed",
    "partially_closed",
    "open",
    "invalidated",
    "expired",
    "cancelled",
    "ambiguous",
]

EquityCurveMode = Literal[
    "completed_trade",
    "realized_cashflow",
]

DrawdownMode = Literal[
    "absolute_and_percent",
    "absolute_only",
]

TimeGroupPeriod = Literal[
    "daily",
    "weekly",
    "monthly",
]

ExitTypeGroup = Literal[
    "tp",
    "sl",
    "expired",
    "other",
    "unknown",
]

MetricAvailability = Literal[
    "available",
    "unavailable",
    "infinite",
]
