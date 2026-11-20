"""Historical trade simulation configuration (Phase 5.2.2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.exchanges.types import Timeframe
from app.replay.simulation.enums import AmbiguityPolicy, EntryPricePolicy

STRATEGY_CONFIG_VERSION = "trade-sim-v1.0.0"

# Documented defaults when trade plan has no partial-exit allocation.
DEFAULT_TP_ALLOCATIONS: tuple[float, ...] = (0.40, 0.30, 0.30)

QTY_TOLERANCE = 1e-9


class SimulationConfig(BaseModel):
    config_version: str = STRATEGY_CONFIG_VERSION
    """Default entry fill price derivation when zone is present."""
    entry_price_policy: EntryPricePolicy = "exact_reference_price"
    """Same-candle SL/TP ambiguity resolution."""
    ambiguity_policy: AmbiguityPolicy = "conservative_stop_first"
    """Execution / entry monitoring timeframe (must match replay event clock)."""
    execution_timeframe: Timeframe = Timeframe.M5
    """Lower TF used only when ambiguity_policy=use_lower_timeframe_if_available."""
    lower_timeframe: Timeframe = Timeframe.M5
    """Partial TP allocation fractions when plan has no explicit sizes. Sum must be 1.0."""
    tp_allocations: tuple[float, ...] = DEFAULT_TP_ALLOCATIONS
    quantity_tolerance: float = Field(default=QTY_TOLERANCE, gt=0, le=1e-3)
    max_trades_tracked: int = Field(default=2000, ge=10, le=50_000)
    disclaimer: str = (
        "HISTORICAL SIMULATION — NOT REAL ORDERS. Hypothetical fills only; "
        "not guaranteed real-world execution. No fees or P&L in this phase."
    )

    @model_validator(mode="after")
    def validate_allocations(self) -> SimulationConfig:
        if not self.tp_allocations:
            raise ValueError("tp_allocations must not be empty")
        if any(a < 0 for a in self.tp_allocations):
            raise ValueError("tp_allocations must be non-negative")
        total = sum(self.tp_allocations)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"tp_allocations must sum to 1.0, got {total}")
        return self

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


DEFAULT_SIMULATION_CONFIG = SimulationConfig()
