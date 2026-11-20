"""Locked Market Structure strategy configuration (Phase 3.2)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DetectionMode(str, Enum):
    """Only BALANCED is fully implemented in Phase 3.2."""

    BALANCED = "balanced"
    # Reserved for later phases — not implemented yet:
    # AGGRESSIVE = "aggressive"
    # CONSERVATIVE = "conservative"


class StructureConfirmation(str, Enum):
    CLOSE = "close"


# Bump when detection rules change so historical runs stay auditable.
STRATEGY_CONFIG_VERSION = "ms-v1.0.0-balanced"


class MarketStructureConfig(BaseModel):
    """
    Immutable snapshot of structure-detection settings.

    Changing these values changes results; always embed `config_version`
    and `snapshot()` in analysis metadata.
    """

    config_version: str = STRATEGY_CONFIG_VERSION
    swing_left: int = Field(default=3, ge=1, le=20)
    swing_right: int = Field(default=3, ge=1, le=20)
    detection_mode: DetectionMode = DetectionMode.BALANCED
    confirmation: StructureConfirmation = StructureConfirmation.CLOSE
    use_closed_candles_only: bool = True
    displacement_atr_period: int = Field(default=14, ge=1)
    displacement_atr_mult: float = Field(default=1.5, gt=0)
    # Equal high/low tie rule: STRICT means equal neighbour disqualifies pivot.
    equal_extreme_tie_rule: str = "strict_inequality"

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


DEFAULT_STRUCTURE_CONFIG = MarketStructureConfig()
