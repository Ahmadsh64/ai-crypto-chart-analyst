"""Entry zone selection from OB/FVG and structure (Phase 4.3)."""

from __future__ import annotations

from dataclasses import dataclass

from app.analysis.market_structure.models import MarketStructureResult, SwingKind
from app.analysis.ob_fvg.models import (
    FairValueGap,
    FvgStatus,
    ObFvgResult,
    ObStatus,
    OrderBlock,
    ZoneSide,
)
from app.analysis.trade_plan.config import TradePlanConfig
from app.analysis.trade_plan.models import EntryZone


@dataclass(frozen=True)
class _Candidate:
    low: float
    high: float
    entry_type: str
    source: str
    event_key: str
    timeframe: str
    priority: float  # lower is better
    explanation: str


def select_entry(
    *,
    direction: str,
    current_price: float,
    atr_value: float | None,
    setup_ob_fvg: ObFvgResult | None,
    setup_structure: MarketStructureResult | None,
    setup_timeframe: str,
    config: TradePlanConfig,
) -> tuple[EntryZone | None, list[str]]:
    """Pick the nearest valid directional setup zone. Returns (entry, blockers)."""
    blockers: list[str] = []
    if setup_ob_fvg is None and setup_structure is None:
        return None, ["Setup timeframe analysis unavailable for entry."]

    side = ZoneSide.BULLISH if direction == "bullish" else ZoneSide.BEARISH
    candidates: list[_Candidate] = []

    if setup_ob_fvg is not None:
        obs = (
            setup_ob_fvg.bullish_order_blocks
            if side == ZoneSide.BULLISH
            else setup_ob_fvg.bearish_order_blocks
        )
        for ob in obs:
            cand = _from_ob(ob, current_price, atr_value, config)
            if cand is not None:
                candidates.append(cand)

        fvgs = (
            setup_ob_fvg.bullish_fvgs
            if side == ZoneSide.BULLISH
            else setup_ob_fvg.bearish_fvgs
        )
        for fvg in fvgs:
            cand = _from_fvg(fvg, current_price, atr_value, config)
            if cand is not None:
                candidates.append(cand)

    if config.allow_structure_retest_entry and setup_structure is not None:
        cand = _from_structure_retest(
            setup_structure,
            direction=direction,
            current_price=current_price,
            atr_value=atr_value,
            timeframe=setup_timeframe,
            config=config,
        )
        if cand is not None:
            candidates.append(cand)

    if not candidates:
        return None, ["No valid entry zone (active OB/FVG or structure retest) near price."]

    candidates.sort(key=lambda c: c.priority)
    best = candidates[0]

    if atr_value and atr_value > 0:
        mid = (best.low + best.high) / 2.0
        dist_atr = abs(mid - current_price) / atr_value
        if dist_atr > config.max_entry_distance_atr and not (
            best.low <= current_price <= best.high
        ):
            return None, [
                f"Nearest entry zone is {dist_atr:.2f} ATR from price "
                f"(max {config.max_entry_distance_atr})."
            ]

    inside = best.low <= current_price <= best.high
    if inside and config.allow_market_condition_entry:
        reference = current_price
        entry_type = "market_condition" if best.entry_type != "structure_retest" else best.entry_type
        explanation = (
            f"Price is inside {best.source}; market-condition reference uses current price. "
            f"{best.explanation}"
        )
    else:
        reference = (best.low + best.high) / 2.0
        entry_type = best.entry_type
        explanation = best.explanation
        if inside:
            reference = current_price
            explanation = f"Price inside zone; reference=current. {best.explanation}"

    if best.low >= best.high:
        return None, ["Entry zone bounds are invalid (low >= high)."]

    return (
        EntryZone(
            entry_low=best.low,
            entry_high=best.high,
            entry_reference_price=reference,
            entry_type=entry_type,  # type: ignore[arg-type]
            entry_source=best.source,
            source_event_key=best.event_key,
            timeframe=setup_timeframe,
            entry_explanation=explanation,
            price_inside_zone=inside,
        ),
        [],
    )


def _zone_allowed_ob(status: ObStatus, config: TradePlanConfig) -> bool:
    if status == ObStatus.ACTIVE:
        return True
    if status == ObStatus.PARTIALLY_MITIGATED and config.allow_partially_active_zones:
        return True
    return False


def _zone_allowed_fvg(status: FvgStatus, config: TradePlanConfig) -> bool:
    if status == FvgStatus.ACTIVE:
        return True
    if status == FvgStatus.PARTIALLY_FILLED and config.allow_partially_active_zones:
        return True
    return False


def _priority(mid: float, current_price: float, atr_value: float | None, base: float) -> float:
    dist = abs(mid - current_price)
    if atr_value and atr_value > 0:
        return base + dist / atr_value
    return base + dist


def _from_ob(
    ob: OrderBlock,
    current_price: float,
    atr_value: float | None,
    config: TradePlanConfig,
) -> _Candidate | None:
    if not ob.confirmed:
        return None
    if not _zone_allowed_ob(ob.status, config):
        return None
    if ob.zone_low >= ob.zone_high:
        return None
    mid = (ob.zone_low + ob.zone_high) / 2.0
    base = 0.0 if ob.status == ObStatus.ACTIVE else 0.5
    return _Candidate(
        low=ob.zone_low,
        high=ob.zone_high,
        entry_type="order_block",
        source=f"{ob.side.value}_order_block:{ob.status.value}",
        event_key=ob.event_key,
        timeframe=ob.timeframe.value,
        priority=_priority(mid, current_price, atr_value, base),
        explanation=(
            f"{ob.timeframe.value} {ob.side.value} order block ({ob.status.value}) "
            f"zone [{ob.zone_low:.6g}, {ob.zone_high:.6g}]."
        ),
    )


def _from_fvg(
    fvg: FairValueGap,
    current_price: float,
    atr_value: float | None,
    config: TradePlanConfig,
) -> _Candidate | None:
    if not fvg.confirmed:
        return None
    if not _zone_allowed_fvg(fvg.status, config):
        return None
    if fvg.zone_low >= fvg.zone_high:
        return None
    mid = (fvg.zone_low + fvg.zone_high) / 2.0
    base = 0.2 if fvg.status == FvgStatus.ACTIVE else 0.7
    return _Candidate(
        low=fvg.zone_low,
        high=fvg.zone_high,
        entry_type="fair_value_gap",
        source=f"{fvg.side.value}_fvg:{fvg.status.value}",
        event_key=fvg.event_key,
        timeframe=fvg.timeframe.value,
        priority=_priority(mid, current_price, atr_value, base),
        explanation=(
            f"{fvg.timeframe.value} {fvg.side.value} FVG ({fvg.status.value}) "
            f"zone [{fvg.zone_low:.6g}, {fvg.zone_high:.6g}]."
        ),
    )


def _from_structure_retest(
    structure: MarketStructureResult,
    *,
    direction: str,
    current_price: float,
    atr_value: float | None,
    timeframe: str,
    config: TradePlanConfig,
) -> _Candidate | None:
    snap = structure.snapshot
    if direction == "bullish":
        level = snap.active_unbroken_swing_low
        swings = [
            s
            for s in structure.swings
            if s.confirmed and s.kind == SwingKind.LOW and s.price is not None
        ]
    else:
        level = snap.active_unbroken_swing_high
        swings = [
            s
            for s in structure.swings
            if s.confirmed and s.kind == SwingKind.HIGH and s.price is not None
        ]
    price = level
    event_key = None
    if price is None and swings:
        # nearest confirmed swing on the correct side of price for a retest
        if direction == "bullish":
            below = [s for s in swings if s.price < current_price]
            pick = max(below, key=lambda s: s.price) if below else None
        else:
            above = [s for s in swings if s.price > current_price]
            pick = min(above, key=lambda s: s.price) if above else None
        if pick is None:
            return None
        price = pick.price
        event_key = pick.event_key
    if price is None:
        return None

    # Thin retest band around the level (±0.15 ATR or 0.05%)
    half = (atr_value * 0.15) if atr_value and atr_value > 0 else price * 0.0005
    low, high = price - half, price + half
    mid = price
    return _Candidate(
        low=low,
        high=high,
        entry_type="structure_retest",
        source="structure_retest",
        event_key=event_key or f"structure_retest:{timeframe}:{price}",
        timeframe=timeframe,
        priority=_priority(mid, current_price, atr_value, 1.0),
        explanation=(
            f"{timeframe} structure retest around confirmed swing level {price:.6g}."
        ),
    )
