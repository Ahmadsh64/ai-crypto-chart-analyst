"""HH / LH / HL / LL classification for confirmed swings."""

from __future__ import annotations

from app.analysis.market_structure.models import StructureLabel, SwingKind, SwingPoint


def classify_swings(swings: list[SwingPoint]) -> list[SwingPoint]:
    """
    Classify each confirmed swing relative to the previous swing of the same kind.

    - Swing High vs previous Swing High → HH or LH
    - Swing Low vs previous Swing Low → HL or LL
    - First swing of each kind remains unclassified (classification=None)
    - Equal price vs previous → LH for highs / HL for lows (deterministic,
      treats flat as non-expansion in the prior direction)
    """
    last_high: SwingPoint | None = None
    last_low: SwingPoint | None = None
    out: list[SwingPoint] = []

    for swing in swings:
        if not swing.confirmed:
            out.append(swing)
            continue

        if swing.kind == SwingKind.HIGH:
            if last_high is None:
                classified = swing.model_copy(
                    update={"classification": None, "previous_swing_key": None, "previous_swing_price": None}
                )
            else:
                label = StructureLabel.HH if swing.price > last_high.price else StructureLabel.LH
                classified = swing.model_copy(
                    update={
                        "classification": label,
                        "previous_swing_key": last_high.event_key,
                        "previous_swing_price": last_high.price,
                    }
                )
            last_high = classified
            out.append(classified)
        else:
            if last_low is None:
                classified = swing.model_copy(
                    update={"classification": None, "previous_swing_key": None, "previous_swing_price": None}
                )
            else:
                label = StructureLabel.HL if swing.price > last_low.price else StructureLabel.LL
                classified = swing.model_copy(
                    update={
                        "classification": label,
                        "previous_swing_key": last_low.event_key,
                        "previous_swing_price": last_low.price,
                    }
                )
            last_low = classified
            out.append(classified)

    return out


def derive_bias_from_swings(swings: list[SwingPoint]) -> "StructureBias":
    """
    Initial / ongoing bias from classified swings.

    - BULLISH when latest classified SH is HH and latest classified SL is HL
    - BEARISH when latest classified SH is LH and latest classified SL is LL
    - Otherwise UNDEFINED (insufficient or mixed evidence)
    """
    from app.analysis.market_structure.models import StructureBias, StructureLabel

    last_h_label: StructureLabel | None = None
    last_l_label: StructureLabel | None = None
    for s in swings:
        if s.kind == SwingKind.HIGH and s.classification is not None:
            last_h_label = s.classification
        if s.kind == SwingKind.LOW and s.classification is not None:
            last_l_label = s.classification

    if last_h_label == StructureLabel.HH and last_l_label == StructureLabel.HL:
        return StructureBias.BULLISH
    if last_h_label == StructureLabel.LH and last_l_label == StructureLabel.LL:
        return StructureBias.BEARISH
    return StructureBias.UNDEFINED
