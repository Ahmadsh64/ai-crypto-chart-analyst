"""Price / decision integrity checks against the immutable analysis snapshot."""

from __future__ import annotations

import math
import re
from typing import Any

from app.ai.explainer.schemas import AnalysisExplanation
from app.ai.explainer.snapshot import AnalysisSnapshot

_PRICE_RE = re.compile(
    r"(?i)\b(?:entry|stop(?:\s*loss)?|sl|tp\s*[123]?|take\s*profit)\b[^0-9]{0,24}([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)"
)


def _near(a: float, b: float, rel: float = 1e-4, abs_tol: float = 1e-6) -> bool:
    return abs(a - b) <= max(abs_tol, rel * max(abs(a), abs(b), 1.0))


def snapshot_allowed_prices(snapshot: AnalysisSnapshot) -> set[float]:
    vals: set[float] = set()
    for v in (
        snapshot.entry_reference_price,
        snapshot.entry_low,
        snapshot.entry_high,
        snapshot.stop_loss_price,
        *snapshot.take_profit_prices,
    ):
        if isinstance(v, (int, float)) and math.isfinite(float(v)):
            vals.add(float(v))
    return vals


def sanitize_explanation(
    explanation: AnalysisExplanation,
    snapshot: AnalysisSnapshot,
) -> AnalysisExplanation:
    """Reject unauthorized invented prices found in free text; never mutate snapshot."""
    warnings: list[str] = list(explanation.validation_warnings)
    allowed = snapshot_allowed_prices(snapshot)
    texts: list[str] = [
        explanation.summary,
        explanation.decision_explanation,
        explanation.market_context,
        explanation.entry_explanation,
        explanation.stop_loss_explanation,
        *explanation.take_profit_explanations,
        *explanation.bullish_evidence,
        *explanation.bearish_evidence,
        *explanation.supporting_factors,
        *explanation.conflicting_factors,
        *explanation.risk_notes,
    ]
    invented: list[str] = []
    for text in texts:
        for match in _PRICE_RE.finditer(text or ""):
            raw = match.group(1).replace(",", "")
            try:
                price = float(raw)
            except ValueError:
                continue
            if allowed and not any(_near(price, a) for a in allowed):
                invented.append(raw)

    if invented:
        warnings.append(
            "Explanation mentioned price-like values not present in the deterministic "
            f"snapshot (ignored for trading levels): {', '.join(sorted(set(invented))[:8])}"
        )

    # Force disclaimer and strip any attempt to claim execution.
    disclaimer = explanation.disclaimer or ""
    if "executed" in (explanation.summary or "").lower() and "not" not in (
        explanation.summary or ""
    ).lower():
        warnings.append("Execution language sanitized — analysis only.")
    if "Analysis only" not in disclaimer:
        disclaimer = (
            "Analysis only — not an executed trade. Entry/SL/TP come from deterministic "
            "engines, not from this explanation text."
        )

    return explanation.model_copy(
        update={
            "validation_warnings": warnings,
            "disclaimer": disclaimer,
            # Ensure decision text mirrors snapshot decision token.
            "decision_explanation": explanation.decision_explanation
            or f"Deterministic decision is {snapshot.decision}.",
        }
    )


def extract_forbidden_price_claims(payload: dict[str, Any]) -> list[str]:
    """Detect model JSON fields that try to set trading levels."""
    forbidden_keys = {
        "entry",
        "entry_price",
        "stop_loss",
        "stop_loss_price",
        "take_profit",
        "take_profit_prices",
        "tp1",
        "tp2",
        "tp3",
        "new_entry",
        "recommended_entry",
    }
    hits: list[str] = []
    for key in payload.keys():
        if str(key).lower() in forbidden_keys:
            hits.append(str(key))
    return hits
