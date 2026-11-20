"""Decision setup eligibility (Phase 4.4) — distinct from entry confirmation."""

from __future__ import annotations

from app.analysis.confluence.models import (
    ConflictSeverity,
    ConfluenceResult,
    PreliminaryAssessment,
)
from app.analysis.decision_engine.config import DecisionConfig
from app.analysis.decision_engine.models import DecisionEligibilityResult
from app.analysis.multi_timeframe.models import MultiTimeframeSnapshot
from app.analysis.trade_plan.models import TradePlanResult


def evaluate_decision_eligibility(
    *,
    confluence: ConfluenceResult,
    trade_plan: TradePlanResult,
    mtf_snapshot: MultiTimeframeSnapshot,
    config: DecisionConfig,
) -> DecisionEligibilityResult:
    blockers: list[str] = []
    notes: list[str] = []

    tf_map = {s.timeframe: s for s in mtf_snapshot.timeframes}
    for tf in config.required_timeframes:
        summary = tf_map.get(tf)
        if summary is None:
            blockers.append(f"Required timeframe {tf.value} missing.")
            continue
        if not summary.is_ready:
            blockers.append(f"Required timeframe {tf.value} not ready.")
        if summary.is_stale or summary.data_quality == "stale":
            blockers.append(f"Required timeframe {tf.value} is stale.")

    if mtf_snapshot.overall_status == "unavailable":
        blockers.append("MTF overall status unavailable.")

    assessment = confluence.preliminary_assessment
    strength = confluence.assessment_strength
    if assessment in {
        PreliminaryAssessment.DATA_UNAVAILABLE,
        PreliminaryAssessment.INSUFFICIENT_EVIDENCE,
        PreliminaryAssessment.MIXED,
    }:
        blockers.append(f"Confluence assessment is {assessment.value}.")

    direction = None
    if assessment == PreliminaryAssessment.BULLISH_CONFLUENCE:
        direction = "bullish"
        lead, trail = confluence.bullish_score, confluence.bearish_score
    elif assessment == PreliminaryAssessment.BEARISH_CONFLUENCE:
        direction = "bearish"
        lead, trail = confluence.bearish_score, confluence.bullish_score
    else:
        lead = trail = 0.0

    if direction is not None:
        if config.require_assessment_strength == "strong" and strength != "strong":
            blockers.append(f"Strong confluence required; got strength={strength!r}.")
        if lead < config.min_directional_score:
            blockers.append(
                f"Directional score {lead:.2f} < {config.min_directional_score}."
            )
        if (lead - trail) < config.min_score_margin:
            blockers.append(
                f"Score margin {lead - trail:.2f} < {config.min_score_margin}."
            )
        notes.append(f"Lead={lead:.2f} trail={trail:.2f}.")

    if config.block_critical_conflicts:
        for c in confluence.conflicts:
            if c.severity == ConflictSeverity.CRITICAL:
                blockers.append(f"Critical conflict: {c.conflict_type} — {c.description}")

    if trade_plan.plan_status != "eligible":
        blockers.append(f"Trade plan status is {trade_plan.plan_status}.")
        blockers.extend(trade_plan.validation.blocking_reasons[:5])
    if trade_plan.direction and direction and trade_plan.direction != direction:
        blockers.append(
            f"Trade plan direction {trade_plan.direction} conflicts with "
            f"confluence direction {direction}."
        )
    if trade_plan.risk is None or not trade_plan.risk.meets_minimum_rr:
        blockers.append("Primary RR does not meet minimum requirement.")
    if trade_plan.entry is None or trade_plan.stop_loss is None:
        blockers.append("Trade plan missing entry or stop loss.")
    if not trade_plan.take_profit_targets:
        blockers.append("Trade plan missing take-profit targets.")

    # Dedup
    seen: set[str] = set()
    unique: list[str] = []
    for b in blockers:
        if b not in seen:
            seen.add(b)
            unique.append(b)

    return DecisionEligibilityResult(
        is_setup_valid=len(unique) == 0 and direction is not None,
        direction=direction,
        blocking_reasons=unique,
        notes=notes,
    )
