"""Change of Character (CHoCH) classification relative to structure bias."""

from __future__ import annotations

from app.analysis.market_structure.models import BreakKind, StructureBias, StructureDirection


def classify_break(
    direction: StructureDirection,
    current_bias: StructureBias,
) -> BreakKind:
    """
    - Against an established bias → CHoCH
    - With bias, or while bias is undefined → BOS

    The first structural close-break while bias is UNDEFINED is always BOS
    (it helps establish directional context; it is never CHoCH).
    """
    if current_bias == StructureBias.UNDEFINED:
        return BreakKind.BOS
    if current_bias == StructureBias.BULLISH and direction == StructureDirection.BEARISH:
        return BreakKind.CHOCH
    if current_bias == StructureBias.BEARISH and direction == StructureDirection.BULLISH:
        return BreakKind.CHOCH
    return BreakKind.BOS


def bias_after_break(
    direction: StructureDirection,
    previous_bias: StructureBias,
    break_kind: BreakKind,
) -> StructureBias:
    """
    After a confirmed close-break:
    - CHoCH flips bias to the break direction
    - BOS sets / reinforces bias to the break direction
    """
    if break_kind == BreakKind.CHOCH:
        return (
            StructureBias.BULLISH
            if direction == StructureDirection.BULLISH
            else StructureBias.BEARISH
        )
    # BOS establishes or continues bias in break direction
    return (
        StructureBias.BULLISH
        if direction == StructureDirection.BULLISH
        else StructureBias.BEARISH
    )
