"""Extract and normalize confluence evidence from Phase 3.x engine results."""

from __future__ import annotations

from app.analysis.confluence.config import ConfluenceConfig, EvidenceCategory
from app.analysis.confluence.models import EvidenceDirection, EvidenceItem, EvidenceType
from app.analysis.liquidity.models import LiquidityResult, LiquidityStatus, ReactionHint
from app.analysis.market_structure.models import (
    BreakKind,
    MarketStructureResult,
    StructureBias,
    StructureLabel,
)
from app.analysis.ob_fvg.models import FvgStatus, ObFvgResult, ObStatus, ZoneSide
from app.exchanges.types import Timeframe


def _eid(prefix: str, source_key: str, timeframe: Timeframe) -> str:
    return f"{prefix}:{timeframe.value}:{source_key}"


def extract_structure_evidence(
    result: MarketStructureResult,
    *,
    timeframe: Timeframe,
    category: EvidenceCategory,
    config: ConfluenceConfig,
) -> list[EvidenceItem]:
    out: list[EvidenceItem] = []
    snap = result.snapshot

    if snap.bias == StructureBias.BULLISH:
        out.append(
            EvidenceItem(
                evidence_id=_eid("bias", f"bias:{snap.bias.value}", timeframe),
                evidence_type=EvidenceType.STRUCTURE_BIAS,
                category=category,
                timeframe=timeframe,
                direction=EvidenceDirection.BULLISH,
                strength=config.strength_bias,
                confidence=1.0,
                source_event_key=f"bias:{timeframe.value}:bullish",
                source_timestamp=snap.calculated_at,
                explanation=f"{timeframe.value} structure bias is bullish.",
            )
        )
    elif snap.bias == StructureBias.BEARISH:
        out.append(
            EvidenceItem(
                evidence_id=_eid("bias", f"bias:{snap.bias.value}", timeframe),
                evidence_type=EvidenceType.STRUCTURE_BIAS,
                category=category,
                timeframe=timeframe,
                direction=EvidenceDirection.BEARISH,
                strength=config.strength_bias,
                confidence=1.0,
                source_event_key=f"bias:{timeframe.value}:bearish",
                source_timestamp=snap.calculated_at,
                explanation=f"{timeframe.value} structure bias is bearish.",
            )
        )

    if result.mss_events:
        mss = result.mss_events[-1]
        out.append(
            EvidenceItem(
                evidence_id=_eid("mss", mss.event_key, timeframe),
                evidence_type=EvidenceType.MSS,
                category=category,
                timeframe=timeframe,
                direction=EvidenceDirection(mss.direction.value),
                strength=config.strength_mss,
                confidence=1.0,
                source_event_key=mss.event_key,
                source_timestamp=mss.confirmation_timestamp,
                explanation=f"{timeframe.value} confirmed MSS ({mss.direction.value}).",
                metadata={"broken_level": mss.broken_level},
            )
        )

    bos_events = [b for b in result.bos_events if b.break_kind == BreakKind.BOS]
    if bos_events:
        bos = bos_events[-1]
        out.append(
            EvidenceItem(
                evidence_id=_eid("bos", bos.event_key, timeframe),
                evidence_type=EvidenceType.BOS,
                category=category,
                timeframe=timeframe,
                direction=EvidenceDirection(bos.direction.value),
                strength=config.strength_bos,
                confidence=1.0,
                source_event_key=bos.event_key,
                source_timestamp=bos.confirmation_timestamp,
                explanation=f"{timeframe.value} confirmed BOS ({bos.direction.value}).",
                metadata={"broken_level": bos.broken_level},
            )
        )

    if result.choch_events:
        choch = result.choch_events[-1]
        out.append(
            EvidenceItem(
                evidence_id=_eid("choch", choch.event_key, timeframe),
                evidence_type=EvidenceType.CHOCH,
                category=category,
                timeframe=timeframe,
                direction=EvidenceDirection(choch.direction.value),
                strength=config.strength_choch,
                confidence=1.0,
                source_event_key=choch.event_key,
                source_timestamp=choch.confirmation_timestamp,
                explanation=f"{timeframe.value} confirmed CHoCH ({choch.direction.value}).",
            )
        )

    confirmed = [s for s in result.swings if s.confirmed and s.classification is not None]
    recent = confirmed[-config.max_recent_swings :]
    bull_labels = {StructureLabel.HH, StructureLabel.HL}
    bear_labels = {StructureLabel.LH, StructureLabel.LL}
    bull_n = sum(1 for s in recent if s.classification in bull_labels)
    bear_n = sum(1 for s in recent if s.classification in bear_labels)
    if bull_n >= 2 and bull_n > bear_n:
        key = f"swings:{timeframe.value}:bullish:{bull_n}"
        out.append(
            EvidenceItem(
                evidence_id=_eid("swings", key, timeframe),
                evidence_type=EvidenceType.SWING_LABELS,
                category=category,
                timeframe=timeframe,
                direction=EvidenceDirection.BULLISH,
                strength=config.strength_swing_labels,
                confidence=0.9,
                source_event_key=key,
                source_timestamp=recent[-1].confirmation_timestamp,
                explanation=f"{timeframe.value} recent confirmed swings lean HH/HL ({bull_n}).",
            )
        )
    elif bear_n >= 2 and bear_n > bull_n:
        key = f"swings:{timeframe.value}:bearish:{bear_n}"
        out.append(
            EvidenceItem(
                evidence_id=_eid("swings", key, timeframe),
                evidence_type=EvidenceType.SWING_LABELS,
                category=category,
                timeframe=timeframe,
                direction=EvidenceDirection.BEARISH,
                strength=config.strength_swing_labels,
                confidence=0.9,
                source_event_key=key,
                source_timestamp=recent[-1].confirmation_timestamp,
                explanation=f"{timeframe.value} recent confirmed swings lean LH/LL ({bear_n}).",
            )
        )

    # Exclude unconfirmed swings explicitly as excluded records for explainability
    for s in result.unconfirmed_swings[:5]:
        out.append(
            EvidenceItem(
                evidence_id=_eid("swing-unc", s.event_key, timeframe),
                evidence_type=EvidenceType.SWING_LABELS,
                category=category,
                timeframe=timeframe,
                direction=EvidenceDirection.NEUTRAL,
                strength=0.0,
                confidence=0.0,
                source_event_key=s.event_key,
                source_timestamp=s.candle_timestamp,
                is_confirmed=False,
                is_active=False,
                explanation="Unconfirmed swing excluded from confluence.",
                excluded=True,
                exclusion_reason="unconfirmed_swing",
            )
        )
    return out


def extract_liquidity_evidence(
    result: LiquidityResult,
    *,
    timeframe: Timeframe,
    category: EvidenceCategory,
    config: ConfluenceConfig,
) -> list[EvidenceItem]:
    out: list[EvidenceItem] = []
    sweeps = [s for s in result.sweeps if s.confirmed and s.reaction_hint is not None]
    for sweep in sweeps[-config.max_recent_sweeps :]:
        hint = sweep.reaction_hint
        assert hint is not None
        direction = (
            EvidenceDirection.BULLISH
            if hint == ReactionHint.BULLISH
            else EvidenceDirection.BEARISH
        )
        out.append(
            EvidenceItem(
                evidence_id=_eid("sweep", sweep.event_key, timeframe),
                evidence_type=EvidenceType.LIQUIDITY_SWEEP,
                category=category,
                timeframe=timeframe,
                direction=direction,
                strength=config.strength_sweep,
                confidence=1.0,
                source_event_key=sweep.event_key,
                source_timestamp=sweep.confirmation_timestamp,
                explanation=(
                    f"{timeframe.value} confirmed {sweep.liquidity_type.value.upper()} sweep "
                    f"→ reaction_hint={hint.value} (contextual, not a signal)."
                ),
                metadata={
                    "liquidity_type": sweep.liquidity_type.value,
                    "reaction_hint": hint.value,
                    "level_price": sweep.level_price,
                },
            )
        )

    active_levels = [
        lv
        for lv in list(result.bsl_levels) + list(result.ssl_levels)
        if lv.status == LiquidityStatus.ACTIVE
    ]
    # Cap weak context to one BSL and one SSL representative
    seen_types: set[str] = set()
    for lv in active_levels:
        t = lv.liquidity_type.value
        if t in seen_types:
            continue
        seen_types.add(t)
        # Untouched liquidity: weak opposite pressure (BSL above = bullish magnet / sellside later)
        # Documented as contextual only — direction follows pool type neutrally as "presence".
        # Use neutral-leaning: BSL presence slightly bearish reaction potential only after sweep;
        # here we mark as weak bearish context for BSL (liquidity to be taken by upside),
        # weak bullish for SSL — matching ICT reaction_hint polarity without claiming a sweep.
        direction = (
            EvidenceDirection.BEARISH
            if t == "bsl"
            else EvidenceDirection.BULLISH
        )
        out.append(
            EvidenceItem(
                evidence_id=_eid("lvl", lv.event_key, timeframe),
                evidence_type=EvidenceType.LIQUIDITY_LEVEL,
                category=category,
                timeframe=timeframe,
                direction=direction,
                strength=config.strength_active_level,
                confidence=0.5,
                source_event_key=lv.event_key,
                source_timestamp=None,
                explanation=(
                    f"{timeframe.value} active {t.upper()} level at {lv.price} "
                    "(not a sweep; weak contextual evidence)."
                ),
                metadata={"status": lv.status.value, "price": lv.price},
            )
        )

    for amb in result.ambiguous_crosses[:3]:
        out.append(
            EvidenceItem(
                evidence_id=_eid("amb", amb.event_key, timeframe),
                evidence_type=EvidenceType.LIQUIDITY_SWEEP,
                category=category,
                timeframe=timeframe,
                direction=EvidenceDirection.NEUTRAL,
                strength=0.0,
                confidence=0.0,
                source_event_key=amb.event_key,
                is_confirmed=False,
                is_active=False,
                explanation="Ambiguous liquidity cross excluded (no reaction_hint).",
                excluded=True,
                exclusion_reason="ambiguous_cross",
            )
        )
    return out


def extract_ob_fvg_evidence(
    result: ObFvgResult,
    *,
    timeframe: Timeframe,
    category: EvidenceCategory,
    config: ConfluenceConfig,
) -> list[EvidenceItem]:
    out: list[EvidenceItem] = []

    def _ob_strength(status: ObStatus) -> float | None:
        if status == ObStatus.ACTIVE:
            return config.strength_ob_active
        if status == ObStatus.PARTIALLY_MITIGATED:
            return config.strength_ob_partial
        return None

    def _fvg_strength(status: FvgStatus) -> float | None:
        if status == FvgStatus.ACTIVE:
            return config.strength_fvg_active
        if status == FvgStatus.PARTIALLY_FILLED:
            return config.strength_fvg_partial
        return None

    bull_obs = [o for o in result.bullish_order_blocks if o.confirmed]
    bear_obs = [o for o in result.bearish_order_blocks if o.confirmed]
    for side_list, side in ((bull_obs, ZoneSide.BULLISH), (bear_obs, ZoneSide.BEARISH)):
        kept = 0
        for ob in reversed(side_list):
            strength = _ob_strength(ob.status)
            if strength is None:
                out.append(
                    EvidenceItem(
                        evidence_id=_eid("ob-x", ob.event_key, timeframe),
                        evidence_type=EvidenceType.ORDER_BLOCK,
                        category=category,
                        timeframe=timeframe,
                        direction=EvidenceDirection(side.value),
                        strength=0.0,
                        confidence=0.0,
                        source_event_key=ob.event_key,
                        source_timestamp=ob.detection_timestamp,
                        is_confirmed=True,
                        is_active=False,
                        explanation=f"OB {ob.status.value} excluded from active confluence.",
                        excluded=True,
                        exclusion_reason=f"ob_status:{ob.status.value}",
                    )
                )
                continue
            if kept >= config.max_zones_per_side:
                out.append(
                    EvidenceItem(
                        evidence_id=_eid("ob-cap", ob.event_key, timeframe),
                        evidence_type=EvidenceType.ORDER_BLOCK,
                        category=category,
                        timeframe=timeframe,
                        direction=EvidenceDirection(side.value),
                        strength=0.0,
                        confidence=0.0,
                        source_event_key=ob.event_key,
                        source_timestamp=ob.detection_timestamp,
                        explanation="Additional OB beyond max_zones_per_side excluded.",
                        excluded=True,
                        exclusion_reason="zone_cap",
                    )
                )
                continue
            kept += 1
            out.append(
                EvidenceItem(
                    evidence_id=_eid("ob", ob.event_key, timeframe),
                    evidence_type=EvidenceType.ORDER_BLOCK,
                    category=category,
                    timeframe=timeframe,
                    direction=EvidenceDirection(side.value),
                    strength=strength,
                    confidence=1.0,
                    source_event_key=ob.event_key,
                    source_timestamp=ob.detection_timestamp,
                    is_active=ob.status in {ObStatus.ACTIVE, ObStatus.PARTIALLY_MITIGATED},
                    explanation=(
                        f"{timeframe.value} {side.value} OB ({ob.status.value}) "
                        f"{ob.zone_low}–{ob.zone_high}."
                    ),
                    metadata={
                        "status": ob.status.value,
                        "zone_low": ob.zone_low,
                        "zone_high": ob.zone_high,
                        "source_structure_event_key": ob.source_structure_event_key,
                    },
                )
            )

    for gaps, side in (
        (result.bullish_fvgs, ZoneSide.BULLISH),
        (result.bearish_fvgs, ZoneSide.BEARISH),
    ):
        kept = 0
        for fvg in reversed([g for g in gaps if g.confirmed]):
            strength = _fvg_strength(fvg.status)
            if strength is None:
                out.append(
                    EvidenceItem(
                        evidence_id=_eid("fvg-x", fvg.event_key, timeframe),
                        evidence_type=EvidenceType.FVG,
                        category=category,
                        timeframe=timeframe,
                        direction=EvidenceDirection(side.value),
                        strength=0.0,
                        confidence=0.0,
                        source_event_key=fvg.event_key,
                        source_timestamp=fvg.detection_timestamp,
                        is_active=False,
                        explanation=f"FVG {fvg.status.value} excluded.",
                        excluded=True,
                        exclusion_reason=f"fvg_status:{fvg.status.value}",
                    )
                )
                continue
            if kept >= config.max_zones_per_side:
                continue
            kept += 1
            out.append(
                EvidenceItem(
                    evidence_id=_eid("fvg", fvg.event_key, timeframe),
                    evidence_type=EvidenceType.FVG,
                    category=category,
                    timeframe=timeframe,
                    direction=EvidenceDirection(side.value),
                    strength=strength,
                    confidence=1.0,
                    source_event_key=fvg.event_key,
                    source_timestamp=fvg.detection_timestamp,
                    explanation=(
                        f"{timeframe.value} {side.value} FVG ({fvg.status.value}) "
                        f"fill≤{fvg.max_fill_pct:.0f}%."
                    ),
                    metadata={"status": fvg.status.value, "max_fill_pct": fvg.max_fill_pct},
                )
            )

    for fvg in list(result.provisional_fvgs)[:5]:
        out.append(
            EvidenceItem(
                evidence_id=_eid("fvg-p", fvg.event_key, timeframe),
                evidence_type=EvidenceType.FVG,
                category=category,
                timeframe=timeframe,
                direction=EvidenceDirection(fvg.side.value),
                strength=0.0,
                confidence=0.0,
                source_event_key=fvg.event_key,
                is_confirmed=False,
                explanation="Provisional/forming FVG excluded.",
                excluded=True,
                exclusion_reason="forming_or_unconfirmed",
            )
        )
    return out


def dedupe_evidence(items: list[EvidenceItem]) -> tuple[list[EvidenceItem], list[EvidenceItem]]:
    """Keep first occurrence of each dedupe_key among non-excluded; mark later as excluded."""
    kept: list[EvidenceItem] = []
    excluded: list[EvidenceItem] = []
    seen: set[str] = set()
    for item in items:
        if item.excluded:
            excluded.append(item)
            continue
        key = item.dedupe_key
        if key in seen:
            excluded.append(
                item.model_copy(
                    update={
                        "excluded": True,
                        "exclusion_reason": "duplicate_event_key",
                        "strength": 0.0,
                        "explanation": item.explanation + " [duplicate excluded]",
                    }
                )
            )
            continue
        seen.add(key)
        kept.append(item)
    return kept, excluded
