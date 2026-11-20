"""Backtesting report configuration (Phase 5.2.6)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel

REPORT_VERSION = "backtest-report-v1.0.0"

DISCLAIMER = (
    "HISTORICAL BACKTEST — SIMULATED RESULTS — NOT REAL ORDERS — NOT FINANCIAL ADVICE"
)

# Maximum completed trade rows included inline in the JSON report payload.
# Export endpoints stream the full set.
MAX_INLINE_COMPLETED_TRADES = 500
# Maximum open / incomplete trades surfaced inline.
MAX_INLINE_OPEN_TRADES = 200


class ReportConfig(BaseModel):
    config_version: str = REPORT_VERSION
    disclaimer: str = DISCLAIMER
    max_inline_completed_trades: int = MAX_INLINE_COMPLETED_TRADES
    max_inline_open_trades: int = MAX_INLINE_OPEN_TRADES

    model_config = {"arbitrary_types_allowed": True}

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


DEFAULT_REPORT_CONFIG = ReportConfig()


def format_decimal(value: Decimal | None) -> str | None:
    """Stable decimal → string (no scientific) suitable for CSV / JSON strings."""
    if value is None:
        return None
    return format(value, "f")
