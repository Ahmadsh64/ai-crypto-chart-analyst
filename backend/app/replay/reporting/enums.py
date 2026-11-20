"""Reporting enums (Phase 5.2.6)."""

from __future__ import annotations

from typing import Literal

ExportKind = Literal["summary", "trades", "equity", "drawdown"]

EXPORT_KINDS: tuple[ExportKind, ...] = ("summary", "trades", "equity", "drawdown")
