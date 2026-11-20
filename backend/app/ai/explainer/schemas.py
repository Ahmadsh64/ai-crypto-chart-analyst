"""Structured AI explanation schemas (must be grounded in analysis snapshot)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VisionComparisonSummary(BaseModel):
    status: str  # CONSISTENT | PARTIALLY_CONSISTENT | CONFLICTING | INSUFFICIENT_VISUAL_DATA | SKIPPED
    notes: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)


class AnalysisExplanation(BaseModel):
    status: str
    summary: str = ""
    decision_explanation: str = ""
    market_context: str = ""
    bullish_evidence: list[str] = Field(default_factory=list)
    bearish_evidence: list[str] = Field(default_factory=list)
    supporting_factors: list[str] = Field(default_factory=list)
    conflicting_factors: list[str] = Field(default_factory=list)
    entry_explanation: str = ""
    stop_loss_explanation: str = ""
    take_profit_explanations: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    missing_confirmations: list[str] = Field(default_factory=list)
    data_limitations: list[str] = Field(default_factory=list)
    vision_comparison: VisionComparisonSummary | None = None
    disclaimer: str = (
        "Analysis only — not an executed trade. Entry/SL/TP come from deterministic "
        "engines, not from this explanation text."
    )
    message: str | None = None
    validation_warnings: list[str] = Field(default_factory=list)
