"""Reporting validation helpers (Phase 5.2.6).

Safe filenames, JSON-safe metric guards, no-look-ahead assertions.
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.replay.reporting.models import BacktestReportSnapshot


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class ReportError(ValueError):
    """Report could not be generated from current session state."""


def safe_filename_component(value: str, *, fallback: str = "report") -> str:
    """Sanitize a filename component: strip path separators and unsafe chars."""
    if value is None:
        return fallback
    cleaned = _SAFE_FILENAME_RE.sub("_", value.strip())
    cleaned = cleaned.strip("._")
    return cleaned or fallback


def build_export_filename(
    *,
    symbol: str,
    kind: str,
    extension: str,
    generated_at: datetime,
) -> str:
    sym = safe_filename_component(symbol.replace("/", ""), fallback="SYMBOL")
    k = safe_filename_component(kind, fallback="report")
    date = generated_at.strftime("%Y-%m-%d")
    ext = safe_filename_component(extension.lstrip("."), fallback="bin")
    return f"{sym}_backtest_{k}_{date}.{ext}"


def ensure_finite(value: Any, *, field: str) -> None:
    """Reject NaN / Inf floats early so JSON never emits invalid tokens."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ReportError(f"Non-finite float in report field {field}: {value}")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ReportError(f"Non-finite Decimal in report field {field}: {value}")


def assert_no_future_data(
    snapshot: BacktestReportSnapshot,
    *,
    clock: datetime | None,
) -> None:
    """Verify no trade/exit/drawdown point postdates the replay clock."""
    if clock is None:
        return
    for row in snapshot.completed_trades:
        if row.exit_timestamp and row.exit_timestamp > clock:
            raise ReportError(
                f"Completed trade {row.trade_id} has exit_timestamp > replay clock"
            )
        if row.entry_timestamp and row.entry_timestamp > clock:
            raise ReportError(
                f"Completed trade {row.trade_id} has entry_timestamp > replay clock"
            )
    for row in snapshot.open_trades:
        if row.entry_timestamp and row.entry_timestamp > clock:
            raise ReportError(
                f"Open trade {row.trade_id} has entry_timestamp > replay clock"
            )
    for point in snapshot.equity.completed.points:
        if point.timestamp > clock:
            raise ReportError("Completed equity point postdates replay clock")
    for point in snapshot.equity.cashflow.points:
        if point.timestamp > clock:
            raise ReportError("Cashflow equity point postdates replay clock")
    for point in snapshot.drawdown.points:
        if point.timestamp > clock:
            raise ReportError("Drawdown point postdates replay clock")


def content_fingerprint(snapshot: BacktestReportSnapshot) -> str:
    """Deterministic content fingerprint ignoring volatile metadata fields."""
    import json

    data = snapshot.model_dump(mode="json")
    meta = data.get("metadata", {})
    meta.pop("report_id", None)
    meta.pop("generated_at", None)
    data["metadata"] = meta
    return json.dumps(data, sort_keys=True, default=str, separators=(",", ":"))
