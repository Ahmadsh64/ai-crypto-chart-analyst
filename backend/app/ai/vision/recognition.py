"""Screenshot recognition helpers (Phase 5.4.2.2) — never invent verified market data."""

from __future__ import annotations

import re
from typing import Any

from app.ai.vision.schemas import VisionResult

# Below this confidence the UI must ask the user to confirm/correct.
CONFIRMATION_CONFIDENCE_THRESHOLD = 0.7

_PRICE_RE = re.compile(
    r"(?:\$|USDT\s*)?"
    r"(?P<num>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)"
)


def clamp_confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, f))


def parse_observed_price(raw: Any) -> float | None:
    """Parse a numeric price from model output or OCR label. Never invent."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        f = float(raw)
        return f if f > 0 else None
    text = str(raw).strip().replace(" ", "")
    if not text:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        pass
    m = _PRICE_RE.search(str(raw))
    if not m:
        return None
    try:
        return float(m.group("num").replace(",", ""))
    except ValueError:
        return None


def needs_symbol_confirmation(vision: VisionResult | None) -> bool:
    if vision is None:
        return True
    if not (vision.detected_symbol or "").strip():
        return True
    conf = vision.symbol_confidence
    if conf is None:
        return True
    return conf < CONFIRMATION_CONFIDENCE_THRESHOLD


def needs_timeframe_confirmation(vision: VisionResult | None) -> bool:
    if vision is None:
        return True
    if not (vision.detected_timeframe or "").strip():
        return True
    conf = vision.timeframe_confidence
    if conf is None:
        return True
    return conf < CONFIRMATION_CONFIDENCE_THRESHOLD


def recognition_summary(vision: VisionResult | None) -> dict[str, Any]:
    """Structured recognition view for API responses (OCR estimates only)."""
    if vision is None:
        return {
            "detected_symbol": None,
            "symbol_confidence": None,
            "detected_timeframe": None,
            "timeframe_confidence": None,
            "detected_exchange": None,
            "detected_platform": None,
            "observed_last_price": None,
            "observed_price_confidence": None,
            "observed_price_label": None,
            "needs_symbol_confirmation": True,
            "needs_timeframe_confirmation": True,
            "disclaimer": (
                "Screenshot recognition is unavailable. Confirm symbol and timeframe "
                "manually before deterministic analysis."
            ),
        }
    return {
        "detected_symbol": vision.detected_symbol,
        "symbol_confidence": vision.symbol_confidence,
        "detected_timeframe": vision.detected_timeframe,
        "timeframe_confidence": vision.timeframe_confidence,
        "detected_exchange": vision.detected_exchange,
        "detected_platform": vision.detected_platform,
        "observed_last_price": vision.observed_last_price,
        "observed_price_confidence": vision.observed_price_confidence,
        "observed_price_label": vision.observed_price_label,
        "needs_symbol_confirmation": needs_symbol_confirmation(vision),
        "needs_timeframe_confirmation": needs_timeframe_confirmation(vision),
        "disclaimer": (
            "Screenshot-observed fields are OCR/visual estimates only — "
            "not verified live exchange prices or guaranteed symbol identity."
        ),
    }


def price_discrepancy_pct(
    observed: float | None, verified: float | None
) -> float | None:
    if observed is None or verified is None:
        return None
    if verified == 0:
        return None
    return ((observed - verified) / verified) * 100.0


__all__ = [
    "CONFIRMATION_CONFIDENCE_THRESHOLD",
    "clamp_confidence",
    "needs_symbol_confirmation",
    "needs_timeframe_confirmation",
    "parse_observed_price",
    "price_discrepancy_pct",
    "recognition_summary",
]
