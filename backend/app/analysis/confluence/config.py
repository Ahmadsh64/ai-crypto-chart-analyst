"""Locked confluence scoring configuration (Phase 4.2)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.exchanges.types import Timeframe

STRATEGY_CONFIG_VERSION = "confluence-v1.0.0-balanced"

EvidenceCategory = Literal[
    "htf_context",
    "market_structure",
    "liquidity",
    "ob_fvg",
    "ltf_confirmation",
]

CATEGORY_ORDER: tuple[EvidenceCategory, ...] = (
    "htf_context",
    "market_structure",
    "liquidity",
    "ob_fvg",
    "ltf_confirmation",
)


class ConfluenceConfig(BaseModel):
    config_version: str = STRATEGY_CONFIG_VERSION
    category_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "htf_context": 25.0,
            "market_structure": 25.0,
            "liquidity": 20.0,
            "ob_fvg": 20.0,
            "ltf_confirmation": 10.0,
        }
    )
    """Geometric decay for stacked evidence inside a category (0 < decay ≤ 1)."""
    evidence_decay: float = Field(default=0.5, gt=0, le=1)
    """Effective strength that saturates a category to 100% of its weight."""
    category_saturation: float = Field(default=2.0, gt=0)
    strong_score_threshold: float = Field(default=70.0, ge=0, le=100)
    moderate_score_threshold: float = Field(default=55.0, ge=0, le=100)
    strong_score_gap: float = Field(default=15.0, ge=0, le=100)
    moderate_score_gap: float = Field(default=10.0, ge=0, le=100)
    required_timeframes: tuple[Timeframe, ...] = (Timeframe.H4, Timeframe.H1)
    max_recent_sweeps: int = Field(default=3, ge=1, le=20)
    max_recent_swings: int = Field(default=4, ge=1, le=20)
    max_zones_per_side: int = Field(default=3, ge=1, le=20)

    # Strength table
    strength_bias: float = 0.55
    strength_mss: float = 1.0
    strength_bos: float = 0.85
    strength_choch: float = 0.75
    strength_swing_labels: float = 0.40
    strength_sweep: float = 0.85
    strength_active_level: float = 0.15
    strength_ob_active: float = 0.70
    strength_ob_partial: float = 0.45
    strength_fvg_active: float = 0.60
    strength_fvg_partial: float = 0.35

    @model_validator(mode="after")
    def _validate_weights(self) -> "ConfluenceConfig":
        total = sum(self.category_weights.get(c, 0.0) for c in CATEGORY_ORDER)
        if abs(total - 100.0) > 1e-6:
            raise ValueError(f"category_weights must sum to 100, got {total}")
        if self.moderate_score_threshold > self.strong_score_threshold:
            raise ValueError("moderate_score_threshold must be ≤ strong_score_threshold")
        return self

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def weight(self, category: EvidenceCategory) -> float:
        return float(self.category_weights[category])


DEFAULT_CONFLUENCE_CONFIG = ConfluenceConfig()
