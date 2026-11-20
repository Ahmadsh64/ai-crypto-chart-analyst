"""Locked Liquidity strategy configuration (Phase 3.3.1)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# Clustering diameter constraint + reaction_hint semantics → version bump.
STRATEGY_CONFIG_VERSION = "liq-v1.1.0-balanced"

# Shared REST / WebSocket analysis candle window (closed + forming).
LIQUIDITY_ANALYSIS_CANDLE_LIMIT = 500


class LiquidityConfig(BaseModel):
    """
    Immutable snapshot of liquidity-detection settings.

    Changing these values changes results; always embed `config_version`
    and `snapshot()` in analysis metadata.
    """

    config_version: str = STRATEGY_CONFIG_VERSION
    eq_cluster_min_swings: int = Field(default=2, ge=2, le=20)
    atr_period: int = Field(default=14, ge=1)
    atr_tolerance_mult: float = Field(default=0.15, gt=0)
    fallback_tolerance_pct: float = Field(default=0.001, gt=0)
    min_penetration_atr_mult: float = Field(default=0.05, gt=0)
    min_penetration_fallback_pct: float = Field(default=0.0002, gt=0)
    use_closed_candles_only: bool = True
    analysis_candle_limit: int = Field(
        default=LIQUIDITY_ANALYSIS_CANDLE_LIMIT,
        ge=50,
        le=2000,
        description="Canonical candle window shared by REST and WebSocket runtimes.",
    )

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


DEFAULT_LIQUIDITY_CONFIG = LiquidityConfig()
