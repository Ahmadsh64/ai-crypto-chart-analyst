"""Locked Order Block / FVG strategy configuration (Phase 3.4)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

STRATEGY_CONFIG_VERSION = "obfvg-v1.0.0-balanced"
OB_FVG_ANALYSIS_CANDLE_LIMIT = 500


class ObFvgConfig(BaseModel):
    config_version: str = STRATEGY_CONFIG_VERSION
    atr_period: int = Field(default=14, ge=1)
    ob_max_lookback: int = Field(default=10, ge=1, le=100)
    ob_displacement_atr_mult: float = Field(default=1.0, gt=0)
    ob_boundary_method: Literal["full_candle"] = "full_candle"
    ob_invalidate_on: Literal["close"] = "close"
    fvg_min_gap_atr_mult: float = Field(default=0.1, gt=0)
    fvg_min_gap_fallback_pct: float = Field(default=0.0005, gt=0)
    use_closed_candles_only: bool = True
    analysis_candle_limit: int = Field(default=OB_FVG_ANALYSIS_CANDLE_LIMIT, ge=50, le=2000)

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


DEFAULT_OB_FVG_CONFIG = ObFvgConfig()
