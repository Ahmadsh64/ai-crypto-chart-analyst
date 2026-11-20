"""Stop-loss / invalidation calculation (Phase 4.3)."""

from __future__ import annotations

from app.analysis.market_structure.models import MarketStructureResult, SwingKind
from app.analysis.trade_plan.config import TradePlanConfig
from app.analysis.trade_plan.models import EntryZone, StopLossPlan


def calculate_stop_loss(
    *,
    direction: str,
    entry: EntryZone,
    atr_value: float | None,
    setup_structure: MarketStructureResult | None,
    config: TradePlanConfig,
) -> tuple[StopLossPlan | None, list[str]]:
    blockers: list[str] = []
    buffer = 0.0
    if atr_value is not None and atr_value > 0:
        buffer = atr_value * config.atr_buffer_mult
    else:
        blockers.append("ATR unavailable — using zone-edge invalidation without ATR buffer.")
        # Soft warning only; still allow zone-edge SL with tiny relative buffer
        buffer = entry.entry_reference_price * 0.0005

    raw_level: float | None = None
    source = "entry_zone_invalidation"
    event_key: str | None = entry.source_event_key
    explanation = ""

    if direction == "bullish":
        # Prefer zone low invalidation, then confirmed swing low below entry
        candidates: list[tuple[float, str, str | None, str]] = [
            (
                entry.entry_low - buffer,
                "bullish_zone_invalidation",
                entry.source_event_key,
                (
                    f"Bullish invalidation below entry zone low {entry.entry_low:.6g} "
                    f"minus buffer {buffer:.6g}."
                ),
            )
        ]
        swing_low = _nearest_confirmed_swing(
            setup_structure,
            kind=SwingKind.LOW,
            below=entry.entry_reference_price,
        )
        if swing_low is not None:
            price, key = swing_low
            candidates.append(
                (
                    price - buffer,
                    "confirmed_swing_low",
                    key,
                    (
                        f"Confirmed swing low {price:.6g} minus ATR buffer {buffer:.6g}."
                    ),
                )
            )
            if setup_structure and setup_structure.snapshot.active_unbroken_swing_low is not None:
                lvl = setup_structure.snapshot.active_unbroken_swing_low
                if lvl < entry.entry_reference_price:
                    candidates.append(
                        (
                            lvl - buffer,
                            "active_unbroken_swing_low",
                            None,
                            f"Active unbroken swing low {lvl:.6g} minus buffer {buffer:.6g}.",
                        )
                    )

        # Choose the closest valid SL below entry (tightest that still clears zone)
        valid = [(p, s, k, e) for p, s, k, e in candidates if p < entry.entry_reference_price]
        if not valid:
            return None, ["No stop-loss level below entry reference for bullish plan."]
        # Prefer technical swing if available and still below entry_low - small epsilon
        # otherwise zone invalidation. Sort by distance from entry (ascending = tighter).
        valid.sort(key=lambda x: entry.entry_reference_price - x[0])
        # Prefer not placing SL inside entry zone: require SL < entry_low (or equal to zone edge - buffer)
        outside = [v for v in valid if v[0] < entry.entry_low - 1e-12 or abs(v[0] - (entry.entry_low - buffer)) < 1e-9]
        pick = outside[0] if outside else valid[0]
        raw_level, source, event_key, explanation = pick

    else:
        candidates = [
            (
                entry.entry_high + buffer,
                "bearish_zone_invalidation",
                entry.source_event_key,
                (
                    f"Bearish invalidation above entry zone high {entry.entry_high:.6g} "
                    f"plus buffer {buffer:.6g}."
                ),
            )
        ]
        swing_high = _nearest_confirmed_swing(
            setup_structure,
            kind=SwingKind.HIGH,
            above=entry.entry_reference_price,
        )
        if swing_high is not None:
            price, key = swing_high
            candidates.append(
                (
                    price + buffer,
                    "confirmed_swing_high",
                    key,
                    f"Confirmed swing high {price:.6g} plus ATR buffer {buffer:.6g}.",
                )
            )
            if setup_structure and setup_structure.snapshot.active_unbroken_swing_high is not None:
                lvl = setup_structure.snapshot.active_unbroken_swing_high
                if lvl > entry.entry_reference_price:
                    candidates.append(
                        (
                            lvl + buffer,
                            "active_unbroken_swing_high",
                            None,
                            f"Active unbroken swing high {lvl:.6g} plus buffer {buffer:.6g}.",
                        )
                    )

        valid = [(p, s, k, e) for p, s, k, e in candidates if p > entry.entry_reference_price]
        if not valid:
            return None, ["No stop-loss level above entry reference for bearish plan."]
        valid.sort(key=lambda x: x[0] - entry.entry_reference_price)
        outside = [v for v in valid if v[0] > entry.entry_high + 1e-12 or abs(v[0] - (entry.entry_high + buffer)) < 1e-9]
        pick = outside[0] if outside else valid[0]
        raw_level, source, event_key, explanation = pick

    if raw_level is None or not _finite(raw_level):
        return None, ["Stop-loss price is not finite."]

    distance = abs(entry.entry_reference_price - raw_level)
    if distance <= 0:
        return None, ["Stop-loss risk distance is zero or negative."]

    if atr_value and atr_value > 0:
        dist_atr = distance / atr_value
        if dist_atr > config.max_stop_distance_atr:
            return None, [
                f"Stop distance {dist_atr:.2f} ATR exceeds max {config.max_stop_distance_atr}."
            ]
        if dist_atr < config.min_stop_distance_atr:
            return None, [
                f"Stop distance {dist_atr:.2f} ATR below min {config.min_stop_distance_atr}."
            ]

    # Reject SL sitting deep inside entry zone without documented zone-edge reason
    if direction == "bullish":
        if entry.entry_low < raw_level < entry.entry_high and source != "bullish_zone_invalidation":
            return None, ["Stop loss sits inside entry zone without zone-edge invalidation."]
        if raw_level >= entry.entry_reference_price:
            return None, ["Bullish stop loss must be below entry reference."]
    else:
        if entry.entry_low < raw_level < entry.entry_high and source != "bearish_zone_invalidation":
            return None, ["Stop loss sits inside entry zone without zone-edge invalidation."]
        if raw_level <= entry.entry_reference_price:
            return None, ["Bearish stop loss must be above entry reference."]

    pct = distance / entry.entry_reference_price * 100.0 if entry.entry_reference_price else 0.0
    plan = StopLossPlan(
        stop_loss_price=raw_level,
        stop_loss_source=source,
        stop_loss_distance=distance,
        stop_loss_distance_pct=pct,
        atr_value=atr_value,
        buffer_value=buffer,
        invalidation_explanation=explanation,
        source_event_key=event_key,
    )
    return plan, blockers if "ATR unavailable" in "".join(blockers) else []


def _nearest_confirmed_swing(
    structure: MarketStructureResult | None,
    *,
    kind: SwingKind,
    below: float | None = None,
    above: float | None = None,
) -> tuple[float, str] | None:
    if structure is None:
        return None
    swings = [s for s in structure.swings if s.confirmed and s.kind == kind]
    if below is not None:
        pool = [s for s in swings if s.price < below]
        if not pool:
            return None
        pick = max(pool, key=lambda s: s.price)
        return pick.price, pick.event_key
    if above is not None:
        pool = [s for s in swings if s.price > above]
        if not pool:
            return None
        pick = min(pool, key=lambda s: s.price)
        return pick.price, pick.event_key
    return None


def _finite(value: float) -> bool:
    return value == value and abs(value) != float("inf")
