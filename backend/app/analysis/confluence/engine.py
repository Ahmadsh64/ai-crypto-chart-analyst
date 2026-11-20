"""Deterministic confluence engine (Phase 4.2)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.analysis.confluence.config import DEFAULT_CONFLUENCE_CONFIG, ConfluenceConfig
from app.analysis.confluence.conflicts import detect_conflicts
from app.analysis.confluence.evidence import (
    dedupe_evidence,
    extract_liquidity_evidence,
    extract_ob_fvg_evidence,
    extract_structure_evidence,
)
from app.analysis.confluence.models import (
    ConfluenceDataQuality,
    ConfluenceResult,
    ConflictSeverity,
    EvidenceDirection,
    EvidenceItem,
)
from app.analysis.confluence.scoring import decide_preliminary_assessment, net_direction, score_categories
from app.analysis.liquidity.models import LiquidityResult
from app.analysis.market_structure.models import MarketStructureResult
from app.analysis.multi_timeframe.models import MultiTimeframeSnapshot
from app.analysis.ob_fvg.models import ObFvgResult
from app.exchanges.types import ExchangeId, MarketType, Timeframe


class TimeframeAnalysisBundle:
    """Per-timeframe engine outputs used for evidence extraction."""

    def __init__(
        self,
        *,
        structure: MarketStructureResult | None = None,
        liquidity: LiquidityResult | None = None,
        ob_fvg: ObFvgResult | None = None,
        structure_error: str | None = None,
        liquidity_error: str | None = None,
        ob_fvg_error: str | None = None,
    ) -> None:
        self.structure = structure
        self.liquidity = liquidity
        self.ob_fvg = ob_fvg
        self.structure_error = structure_error
        self.liquidity_error = liquidity_error
        self.ob_fvg_error = ob_fvg_error


def _build_summary(
    assessment: PreliminaryAssessment,
    evidence: list[EvidenceItem],
    conflicts: list,
    bullish: float,
    bearish: float,
) -> str:
    parts: list[str] = []
    active = [e for e in evidence if not e.excluded]
    # Prefer strongest bullish / bearish explanations
    bulls = sorted(
        (e for e in active if e.direction == EvidenceDirection.BULLISH),
        key=lambda x: x.strength * x.confidence,
        reverse=True,
    )
    bears = sorted(
        (e for e in active if e.direction == EvidenceDirection.BEARISH),
        key=lambda x: x.strength * x.confidence,
        reverse=True,
    )
    if bulls:
        parts.append(bulls[0].explanation)
    if bears:
        parts.append(bears[0].explanation)
    crit = [c for c in conflicts if c.severity == ConflictSeverity.CRITICAL]
    if crit:
        parts.append(crit[0].description)
    parts.append(
        f"Scores bullish={bullish:.1f} bearish={bearish:.1f}; "
        f"preliminary assessment={assessment.value}."
    )
    return " ".join(parts)


def analyze_confluence(
    *,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    mtf_snapshot: MultiTimeframeSnapshot,
    bundles: dict[Timeframe, TimeframeAnalysisBundle],
    config: ConfluenceConfig | None = None,
    as_of: datetime | None = None,
) -> ConfluenceResult:
    cfg = config or DEFAULT_CONFLUENCE_CONFIG
    now = as_of or datetime.now(timezone.utc)

    tf_map = {s.timeframe: s for s in mtf_snapshot.timeframes}
    used: list[Timeframe] = []
    unavailable: list[Timeframe] = []
    stale: list[Timeframe] = []
    limitations: list[str] = []

    raw: list[EvidenceItem] = []

    # 4H HTF
    s4 = tf_map.get(Timeframe.H4)
    if s4 and s4.is_ready and Timeframe.H4 in bundles and bundles[Timeframe.H4].structure:
        used.append(Timeframe.H4)
        raw.extend(
            extract_structure_evidence(
                bundles[Timeframe.H4].structure,  # type: ignore[arg-type]
                timeframe=Timeframe.H4,
                category="htf_context",
                config=cfg,
            )
        )
    else:
        unavailable.append(Timeframe.H4)
        if s4 and s4.is_stale:
            stale.append(Timeframe.H4)
        limitations.append("4H context unavailable or not ready.")

    # 1H structure + liquidity
    s1 = tf_map.get(Timeframe.H1)
    if s1 and s1.is_ready and Timeframe.H1 in bundles:
        b1 = bundles[Timeframe.H1]
        used.append(Timeframe.H1)
        if b1.structure:
            raw.extend(
                extract_structure_evidence(
                    b1.structure,
                    timeframe=Timeframe.H1,
                    category="market_structure",
                    config=cfg,
                )
            )
        else:
            limitations.append(b1.structure_error or "1H structure engine result missing.")
        if b1.liquidity:
            raw.extend(
                extract_liquidity_evidence(
                    b1.liquidity,
                    timeframe=Timeframe.H1,
                    category="liquidity",
                    config=cfg,
                )
            )
        elif b1.liquidity_error:
            limitations.append(b1.liquidity_error)
    else:
        unavailable.append(Timeframe.H1)
        if s1 and s1.is_stale:
            stale.append(Timeframe.H1)
        limitations.append("1H market structure unavailable or not ready.")

    # 15M liquidity + OB/FVG
    s15 = tf_map.get(Timeframe.M15)
    if s15 and s15.is_ready and Timeframe.M15 in bundles:
        b15 = bundles[Timeframe.M15]
        if Timeframe.M15 not in used:
            used.append(Timeframe.M15)
        if b15.liquidity:
            raw.extend(
                extract_liquidity_evidence(
                    b15.liquidity,
                    timeframe=Timeframe.M15,
                    category="liquidity",
                    config=cfg,
                )
            )
        if b15.ob_fvg:
            raw.extend(
                extract_ob_fvg_evidence(
                    b15.ob_fvg,
                    timeframe=Timeframe.M15,
                    category="ob_fvg",
                    config=cfg,
                )
            )
        else:
            limitations.append(b15.ob_fvg_error or "15M OB/FVG result missing.")
    else:
        unavailable.append(Timeframe.M15)
        if s15 and s15.is_stale:
            stale.append(Timeframe.M15)
        limitations.append("15M setup timeframe unavailable or not ready.")

    # 5M confirmation
    s5 = tf_map.get(Timeframe.M5)
    if s5 and s5.is_ready and Timeframe.M5 in bundles:
        b5 = bundles[Timeframe.M5]
        used.append(Timeframe.M5)
        if b5.structure:
            raw.extend(
                extract_structure_evidence(
                    b5.structure,
                    timeframe=Timeframe.M5,
                    category="ltf_confirmation",
                    config=cfg,
                )
            )
        if b5.liquidity:
            raw.extend(
                extract_liquidity_evidence(
                    b5.liquidity,
                    timeframe=Timeframe.M5,
                    category="ltf_confirmation",
                    config=cfg,
                )
            )
        if b5.ob_fvg:
            raw.extend(
                extract_ob_fvg_evidence(
                    b5.ob_fvg,
                    timeframe=Timeframe.M5,
                    category="ltf_confirmation",
                    config=cfg,
                )
            )
    else:
        unavailable.append(Timeframe.M5)
        if s5 and s5.is_stale:
            stale.append(Timeframe.M5)
        limitations.append("5M confirmation timeframe unavailable or not ready.")

    kept, excluded = dedupe_evidence(raw)
    category_scores, bullish_score, bearish_score = score_categories(kept, cfg)

    conflicts = detect_conflicts(
        kept + excluded,
        timeframe_summaries=mtf_snapshot.timeframes,
        required=cfg.required_timeframes,
    )
    has_critical = any(c.severity == ConflictSeverity.CRITICAL for c in conflicts)

    required_ready = all(
        (tf_map.get(tf) is not None and tf_map[tf].is_ready) for tf in cfg.required_timeframes
    )
    data_unavailable = mtf_snapshot.overall_status == "unavailable" or (
        Timeframe.H4 in unavailable and Timeframe.H1 in unavailable
    )
    analysis_complete = required_ready and not data_unavailable

    h4_dir = net_direction([e for e in kept if e.timeframe == Timeframe.H4])
    htf_opposes_bullish = h4_dir == EvidenceDirection.BEARISH
    htf_opposes_bearish = h4_dir == EvidenceDirection.BULLISH

    has_confirmed = any(
        e.is_confirmed and e.direction != EvidenceDirection.NEUTRAL and not e.excluded for e in kept
    )

    assessment, strength = decide_preliminary_assessment(
        bullish_score=bullish_score,
        bearish_score=bearish_score,
        config=cfg,
        has_critical_htf_conflict=has_critical
        and any(c.conflict_type == "htf_structure_conflict" for c in conflicts),
        analysis_complete=analysis_complete,
        data_unavailable=data_unavailable,
        has_confirmed_evidence=has_confirmed,
        htf_opposes_bullish=htf_opposes_bullish,
        htf_opposes_bearish=htf_opposes_bearish,
    )

    dq_overall = mtf_snapshot.overall_status
    if stale:
        dq_overall = "stale"
    elif not analysis_complete:
        dq_overall = "incomplete"

    quality = ConfluenceDataQuality(
        overall=dq_overall,
        is_analysis_complete=analysis_complete,
        timeframes_used=used,
        timeframes_unavailable=sorted(set(unavailable), key=lambda t: t.value),
        timeframes_stale=sorted(set(stale), key=lambda t: t.value),
        limitations=limitations,
    )

    summary = _build_summary(assessment, kept, conflicts, bullish_score, bearish_score)

    return ConfluenceResult(
        exchange=exchange,
        symbol=symbol,
        market_type=market_type,
        calculated_at=now,
        config_version=cfg.config_version,
        bullish_score=bullish_score,
        bearish_score=bearish_score,
        category_scores=category_scores,
        evidence=kept,
        excluded_evidence=excluded,
        conflicts=conflicts,
        preliminary_assessment=assessment,
        assessment_strength=strength,  # type: ignore[arg-type]
        data_quality=quality,
        summary=summary,
        metadata={
            "strategy_phase": "4.2",
            "no_trade_decisions": True,
            "mtf_config_version": mtf_snapshot.config_version,
            "indicators_used": False,
        },
    )
