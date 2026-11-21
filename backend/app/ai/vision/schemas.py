"""Pydantic schemas for Vision observations (observational only)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ObservationCategory(str, Enum):
    TREND = "TREND"
    SUPPORT = "SUPPORT"
    RESISTANCE = "RESISTANCE"
    CANDLE_PATTERN = "CANDLE_PATTERN"
    INDICATOR = "INDICATOR"
    PRICE_ZONE = "PRICE_ZONE"
    ANNOTATION = "ANNOTATION"
    OTHER = "OTHER"


class VisionObservation(BaseModel):
    observation_id: str
    category: ObservationCategory
    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    visible: bool = True
    evidence_description: str = ""
    uncertainty_reason: str | None = None


class VisionImageMetadata(BaseModel):
    content_type: str
    width: int
    height: int
    size_bytes: int
    format: str


class VisionResult(BaseModel):
    status: str
    image_metadata: VisionImageMetadata | None = None
    detected_timeframe: str | None = None
    detected_symbol: str | None = None
    detected_chart_type: str | None = None
    # Phase 5.4.2.2 — screenshot recognition (OCR/visual estimates only)
    detected_exchange: str | None = None
    detected_platform: str | None = None
    symbol_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    timeframe_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    observed_last_price: float | None = None
    observed_price_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    observed_price_label: str | None = None
    observations: list[VisionObservation] = Field(default_factory=list)
    visible_price_labels: list[str] = Field(default_factory=list)
    visible_indicators: list[str] = Field(default_factory=list)
    unreadable_fields: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    message: str | None = None

    @field_validator("visible_price_labels", mode="before")
    @classmethod
    def _stringify_labels(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            return [str(v)]
        return [str(x) for x in v]
