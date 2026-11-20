"""Compare vision observations with live deterministic analysis."""

from __future__ import annotations

from app.ai.explainer.schemas import VisionComparisonSummary
from app.ai.explainer.snapshot import AnalysisSnapshot
from app.ai.vision.schemas import VisionResult


def compare_vision_to_snapshot(
    vision: VisionResult | None,
    snapshot: AnalysisSnapshot,
) -> VisionComparisonSummary:
    if vision is None or vision.status != "OK":
        return VisionComparisonSummary(
            status="INSUFFICIENT_VISUAL_DATA",
            notes=["No valid vision result available for comparison."],
        )

    notes: list[str] = [
        "SCREENSHOT OBSERVATION vs LIVE DETERMINISTIC ANALYSIS",
        "Screenshot prices are not assumed to be current market prices.",
    ]
    disagreements: list[str] = []

    if vision.detected_symbol and snapshot.symbol:
        vs = vision.detected_symbol.upper().replace("-", "/").replace("USDT", "/USDT")
        ss = snapshot.symbol.upper()
        # Loose compare: strip separators
        vn = "".join(ch for ch in vs if ch.isalnum())
        sn = "".join(ch for ch in ss if ch.isalnum())
        if vn and sn and vn not in sn and sn not in vn:
            disagreements.append(
                f"Screenshot symbol observation '{vision.detected_symbol}' "
                f"differs from selected live symbol '{snapshot.symbol}'."
            )

    if vision.detected_timeframe:
        # Snapshot does not carry selected chart TF directly; note limitation.
        notes.append(
            f"Screenshot timeframe label appears to be '{vision.detected_timeframe}' "
            "(compare manually to selected chart timeframe)."
        )

    obs_text = " ".join(o.description.lower() for o in vision.observations)
    decision = snapshot.decision.upper()
    if "bull" in obs_text and decision in {"SHORT", "NO TRADE"}:
        disagreements.append(
            "Screenshot observations lean bullish while live decision is "
            f"{decision}."
        )
    if "bear" in obs_text and decision in {"LONG", "NO TRADE"}:
        disagreements.append(
            "Screenshot observations lean bearish while live decision is "
            f"{decision}."
        )

    if not vision.observations and not vision.visible_price_labels:
        return VisionComparisonSummary(
            status="INSUFFICIENT_VISUAL_DATA",
            notes=notes + ["Vision returned no usable observations."],
            disagreements=disagreements,
        )

    if disagreements:
        status = "CONFLICTING" if len(disagreements) >= 2 else "PARTIALLY_CONSISTENT"
    else:
        status = "CONSISTENT"

    return VisionComparisonSummary(
        status=status,
        notes=notes,
        disagreements=disagreements,
    )
