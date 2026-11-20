"""Category scoring with decay saturation and weight caps (Phase 4.2)."""

from __future__ import annotations

from app.analysis.confluence.config import CATEGORY_ORDER, ConfluenceConfig, EvidenceCategory
from app.analysis.confluence.models import (
    CategoryScore,
    EvidenceDirection,
    EvidenceItem,
    PreliminaryAssessment,
)


def _side_unit(items: list[EvidenceItem], config: ConfluenceConfig) -> tuple[float, list[str]]:
    ranked = sorted(
        (i for i in items if not i.excluded and i.direction != EvidenceDirection.NEUTRAL),
        key=lambda x: x.strength * x.confidence,
        reverse=True,
    )
    effective = 0.0
    decay = config.evidence_decay
    ids: list[str] = []
    for i, item in enumerate(ranked):
        effective += item.strength * item.confidence * (decay**i)
        ids.append(item.evidence_id)
    unit = min(1.0, effective / config.category_saturation) if config.category_saturation else 0.0
    return unit, ids


def score_categories(
    evidence: list[EvidenceItem],
    config: ConfluenceConfig,
) -> tuple[list[CategoryScore], float, float]:
    category_scores: list[CategoryScore] = []
    bullish_total = 0.0
    bearish_total = 0.0

    for category in CATEGORY_ORDER:
        weight = config.weight(category)
        cat_items = [e for e in evidence if e.category == category and not e.excluded]
        bull = [e for e in cat_items if e.direction == EvidenceDirection.BULLISH]
        bear = [e for e in cat_items if e.direction == EvidenceDirection.BEARISH]
        bull_unit, bull_ids = _side_unit(bull, config)
        bear_unit, bear_ids = _side_unit(bear, config)
        bull_c = min(weight, bull_unit * weight)
        bear_c = min(weight, bear_unit * weight)
        category_scores.append(
            CategoryScore(
                category=category,
                weight=weight,
                bullish_contribution=round(bull_c, 4),
                bearish_contribution=round(bear_c, 4),
                bullish_unit=round(bull_unit, 6),
                bearish_unit=round(bear_unit, 6),
                bullish_evidence_ids=bull_ids,
                bearish_evidence_ids=bear_ids,
            )
        )
        bullish_total += bull_c
        bearish_total += bear_c

    return (
        category_scores,
        round(min(100.0, bullish_total), 4),
        round(min(100.0, bearish_total), 4),
    )


def net_direction(items: list[EvidenceItem]) -> EvidenceDirection | None:
    bull = sum(i.strength * i.confidence for i in items if i.direction == EvidenceDirection.BULLISH and not i.excluded)
    bear = sum(i.strength * i.confidence for i in items if i.direction == EvidenceDirection.BEARISH and not i.excluded)
    if bull <= 0 and bear <= 0:
        return None
    if abs(bull - bear) < 1e-9:
        return None
    return EvidenceDirection.BULLISH if bull > bear else EvidenceDirection.BEARISH


def decide_preliminary_assessment(
    *,
    bullish_score: float,
    bearish_score: float,
    config: ConfluenceConfig,
    has_critical_htf_conflict: bool,
    analysis_complete: bool,
    data_unavailable: bool,
    has_confirmed_evidence: bool,
    htf_opposes_bullish: bool,
    htf_opposes_bearish: bool,
) -> tuple[PreliminaryAssessment, str]:
    if data_unavailable:
        return PreliminaryAssessment.DATA_UNAVAILABLE, "none"
    if not analysis_complete:
        return PreliminaryAssessment.INSUFFICIENT_EVIDENCE, "none"
    if has_critical_htf_conflict:
        return PreliminaryAssessment.MIXED, "none"
    if not has_confirmed_evidence:
        return PreliminaryAssessment.INSUFFICIENT_EVIDENCE, "none"

    lead_bull = bullish_score >= bearish_score
    lead = bullish_score if lead_bull else bearish_score
    trail = bearish_score if lead_bull else bullish_score
    gap = lead - trail

    if lead_bull and htf_opposes_bullish:
        return PreliminaryAssessment.MIXED, "none"
    if (not lead_bull) and htf_opposes_bearish:
        return PreliminaryAssessment.MIXED, "none"

    if lead >= config.strong_score_threshold and gap >= config.strong_score_gap:
        label = (
            PreliminaryAssessment.BULLISH_CONFLUENCE
            if lead_bull
            else PreliminaryAssessment.BEARISH_CONFLUENCE
        )
        return label, "strong"
    if lead >= config.moderate_score_threshold and gap >= config.moderate_score_gap:
        label = (
            PreliminaryAssessment.BULLISH_CONFLUENCE
            if lead_bull
            else PreliminaryAssessment.BEARISH_CONFLUENCE
        )
        return label, "moderate"
    return PreliminaryAssessment.MIXED, "none"
