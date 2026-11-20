"""Explicit confluence conflict detection (Phase 4.2)."""

from __future__ import annotations

from app.analysis.confluence.models import (
    ConflictItem,
    ConflictSeverity,
    EvidenceDirection,
    EvidenceItem,
    EvidenceType,
)
from app.analysis.confluence.scoring import net_direction
from app.analysis.multi_timeframe.models import TimeframeSeriesSummary
from app.exchanges.types import Timeframe


def _ids(items: list[EvidenceItem], direction: EvidenceDirection) -> list[str]:
    return [i.evidence_id for i in items if i.direction == direction and not i.excluded]


def detect_conflicts(
    evidence: list[EvidenceItem],
    *,
    timeframe_summaries: list[TimeframeSeriesSummary],
    required: tuple[Timeframe, ...],
) -> list[ConflictItem]:
    conflicts: list[ConflictItem] = []
    active = [e for e in evidence if not e.excluded]

    by_tf: dict[Timeframe, list[EvidenceItem]] = {}
    for e in active:
        by_tf.setdefault(e.timeframe, []).append(e)

    h4 = by_tf.get(Timeframe.H4, [])
    h1 = by_tf.get(Timeframe.H1, [])
    m15 = by_tf.get(Timeframe.M15, [])
    m5 = by_tf.get(Timeframe.M5, [])

    h4_dir = net_direction(h4)
    h1_dir = net_direction(h1)
    m15_dir = net_direction(m15)
    m5_dir = net_direction(m5)

    if (
        h4_dir is not None
        and h1_dir is not None
        and h4_dir != h1_dir
        and h4_dir != EvidenceDirection.NEUTRAL
        and h1_dir != EvidenceDirection.NEUTRAL
    ):
        conflicts.append(
            ConflictItem(
                conflict_type="htf_structure_conflict",
                severity=ConflictSeverity.CRITICAL,
                affected_timeframes=[Timeframe.H4, Timeframe.H1],
                bullish_evidence_ids=_ids(h4 + h1, EvidenceDirection.BULLISH),
                bearish_evidence_ids=_ids(h4 + h1, EvidenceDirection.BEARISH),
                description=(
                    f"4H net {h4_dir.value} versus 1H net {h1_dir.value} — "
                    "higher-timeframe structure conflict."
                ),
            )
        )

    if h1_dir is not None and m15_dir is not None and h1_dir != m15_dir:
        conflicts.append(
            ConflictItem(
                conflict_type="structure_setup_conflict",
                severity=ConflictSeverity.HIGH,
                affected_timeframes=[Timeframe.H1, Timeframe.M15],
                bullish_evidence_ids=_ids(h1 + m15, EvidenceDirection.BULLISH),
                bearish_evidence_ids=_ids(h1 + m15, EvidenceDirection.BEARISH),
                description=f"1H net {h1_dir.value} versus 15M net {m15_dir.value}.",
            )
        )

    if m15_dir is not None and m5_dir is not None and m15_dir != m5_dir:
        conflicts.append(
            ConflictItem(
                conflict_type="setup_entry_conflict",
                severity=ConflictSeverity.MEDIUM,
                affected_timeframes=[Timeframe.M15, Timeframe.M5],
                bullish_evidence_ids=_ids(m15 + m5, EvidenceDirection.BULLISH),
                bearish_evidence_ids=_ids(m15 + m5, EvidenceDirection.BEARISH),
                description=(
                    f"15M net {m15_dir.value} versus 5M net {m5_dir.value}. "
                    "5M cannot erase higher-TF context."
                ),
            )
        )

    sweeps = [e for e in active if e.evidence_type == EvidenceType.LIQUIDITY_SWEEP]
    if any(e.direction == EvidenceDirection.BULLISH for e in sweeps) and any(
        e.direction == EvidenceDirection.BEARISH for e in sweeps
    ):
        conflicts.append(
            ConflictItem(
                conflict_type="liquidity_dual",
                severity=ConflictSeverity.MEDIUM,
                affected_timeframes=sorted({e.timeframe for e in sweeps}, key=lambda t: t.value),
                bullish_evidence_ids=_ids(sweeps, EvidenceDirection.BULLISH),
                bearish_evidence_ids=_ids(sweeps, EvidenceDirection.BEARISH),
                description="Confirmed bullish and bearish liquidity sweeps present.",
            )
        )

    zones = [
        e
        for e in active
        if e.evidence_type in {EvidenceType.ORDER_BLOCK, EvidenceType.FVG} and e.is_active
    ]
    if any(e.direction == EvidenceDirection.BULLISH for e in zones) and any(
        e.direction == EvidenceDirection.BEARISH for e in zones
    ):
        conflicts.append(
            ConflictItem(
                conflict_type="ob_fvg_dual",
                severity=ConflictSeverity.MEDIUM,
                affected_timeframes=[Timeframe.M15],
                bullish_evidence_ids=_ids(zones, EvidenceDirection.BULLISH),
                bearish_evidence_ids=_ids(zones, EvidenceDirection.BEARISH),
                description="Material bullish and bearish OB/FVG zones are both active.",
            )
        )

    summary_by_tf = {s.timeframe: s for s in timeframe_summaries}
    for tf in required:
        s = summary_by_tf.get(tf)
        if s is None or s.data_quality in {"unavailable", "error", "insufficient"}:
            conflicts.append(
                ConflictItem(
                    conflict_type="missing_timeframe",
                    severity=(
                        ConflictSeverity.CRITICAL
                        if tf in required
                        else ConflictSeverity.HIGH
                    ),
                    affected_timeframes=[tf],
                    description=(
                        f"Required timeframe {tf.value} unavailable "
                        f"({s.data_quality if s else 'missing'})."
                    ),
                )
            )
        elif s.is_stale or s.data_quality == "stale":
            conflicts.append(
                ConflictItem(
                    conflict_type="stale_timeframe",
                    severity=ConflictSeverity.HIGH,
                    affected_timeframes=[tf],
                    description=f"Required timeframe {tf.value} is stale.",
                )
            )

    return conflicts
