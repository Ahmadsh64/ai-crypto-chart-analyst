"""Execution cost enums (Phase 5.2.3)."""

from __future__ import annotations

from typing import Literal

FeeConfigSource = Literal["user", "environment", "example_default"]

SlippagePolicy = Literal["none", "fixed_bps", "percentage", "conservative_ohlcv"]

SpreadPolicy = Literal["none", "fixed_bps", "percentage", "synthetic_assumption"]

MakerTakerClass = Literal["maker", "taker", "unknown"]

MakerTakerFallback = Literal["assume_taker", "assume_maker", "unknown"]

ExecutionRole = Literal["entry", "exit"]

OrderTypeEstimate = Literal["limit", "stop", "marketable_limit", "unknown"]
