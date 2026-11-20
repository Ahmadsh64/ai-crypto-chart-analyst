"""Trade-plan eligibility gates (Phase 4.3)."""

from __future__ import annotations

from app.analysis.confluence.models import (
    ConflictSeverity,
    ConfluenceResult,
    PreliminaryAssessment,
)
from app.analysis.multi_timeframe.models import MultiTimeframeSnapshot
from app.analysis.trade_plan.config import TradePlanConfig
from app.analysis.trade_plan.models import EligibilityResult
from app.exchanges.types import Timeframe


def evaluate_eligibility(
    confluence: ConfluenceResult,
    mtf_snapshot: MultiTimeframeSnapshot,
    *,
    current_price: float | None,
    config: TradePlanConfig,
) -> EligibilityResult:
    blockers: list[str] = []
    notes: list[str] = []

    assessment = confluence.preliminary_assessment
    strength = confluence.assessment_strength
    bull = confluence.bullish_score
    bear = confluence.bearish_score

    if assessment == PreliminaryAssessment.DATA_UNAVAILABLE:
        blockers.append("Confluence data unavailable.")
    if assessment == PreliminaryAssessment.INSUFFICIENT_EVIDENCE:
        blockers.append("Insufficient confirmed confluence evidence.")
    if assessment == PreliminaryAssessment.MIXED:
        blockers.append("Confluence assessment is mixed — no directional plan.")

    directional = assessment in {
        PreliminaryAssessment.BULLISH_CONFLUENCE,
        PreliminaryAssessment.BEARISH_CONFLUENCE,
    }
    if directional:
        if config.require_assessment_strength == "strong" and strength != "strong":
            blockers.append(
                f"Strong directional confluence required; got strength={strength!r}."
            )
        elif config.require_assessment_strength == "moderate" and strength not in {
            "strong",
            "moderate",
        }:
            blockers.append(
                f"Moderate+ directional confluence required; got strength={strength!r}."
            )

    direction = None
    if assessment == PreliminaryAssessment.BULLISH_CONFLUENCE:
        direction = "bullish"
        lead, trail = bull, bear
    elif assessment == PreliminaryAssessment.BEARISH_CONFLUENCE:
        direction = "bearish"
        lead, trail = bear, bull
    else:
        lead = trail = 0.0

    if direction is not None:
        if lead < config.min_directional_score:
            blockers.append(
                f"Directional score {lead:.2f} < minimum {config.min_directional_score}."
            )
        margin = lead - trail
        if margin < config.min_score_margin:
            blockers.append(
                f"Score margin {margin:.2f} < minimum {config.min_score_margin}."
            )
        notes.append(f"Lead score={lead:.2f} trail={trail:.2f} margin={margin:.2f}.")

    if config.block_critical_conflicts:
        critical = [
            c
            for c in confluence.conflicts
            if c.severity == ConflictSeverity.CRITICAL
        ]
        for c in critical:
            blockers.append(f"Critical conflict: {c.conflict_type} — {c.description}")

    tf_map = {s.timeframe: s for s in mtf_snapshot.timeframes}
    for tf in config.required_timeframes:
        summary = tf_map.get(tf)
        if summary is None:
            blockers.append(f"Required timeframe {tf.value} missing from MTF snapshot.")
            continue
        if not summary.is_ready:
            blockers.append(
                f"Required timeframe {tf.value} not ready (quality={summary.data_quality})."
            )
        if summary.is_stale or summary.data_quality == "stale":
            blockers.append(f"Required timeframe {tf.value} is stale.")

    if current_price is None or not _finite_positive(current_price):
        blockers.append("Valid current market price unavailable.")

    confirmed = [
        e
        for e in confluence.evidence
        if not e.excluded and e.is_confirmed and e.direction.value == (direction or "")
    ]
    if direction is not None and not confirmed:
        blockers.append("No confirmed directional evidence for the selected side.")

    # Deduplicate blockers while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for b in blockers:
        if b not in seen:
            seen.add(b)
            unique.append(b)

    return EligibilityResult(
        is_eligible=len(unique) == 0 and direction is not None,
        direction=direction,  # type: ignore[arg-type]
        blocking_reasons=unique,
        notes=notes,
    )


def _finite_positive(value: float) -> bool:
    return value == value and abs(value) != float("inf") and value > 0
