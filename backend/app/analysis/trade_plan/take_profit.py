"""Take-profit target selection (Phase 4.3)."""

from __future__ import annotations

from dataclasses import dataclass

from app.analysis.liquidity.models import LiquidityResult, LiquidityStatus, LiquidityType
from app.analysis.market_structure.models import MarketStructureResult, SwingKind
from app.analysis.ob_fvg.models import FvgStatus, ObFvgResult, ObStatus
from app.analysis.trade_plan.config import TradePlanConfig
from app.analysis.trade_plan.models import EntryZone, StopLossPlan, TakeProfitTarget


@dataclass(frozen=True)
class _TargetCand:
    price: float
    source: str
    event_key: str | None
    explanation: str


def calculate_take_profits(
    *,
    direction: str,
    entry: EntryZone,
    stop: StopLossPlan,
    liquidity_results: list[LiquidityResult],
    structure_results: list[MarketStructureResult],
    opposing_ob_fvg: ObFvgResult | None,
    config: TradePlanConfig,
) -> tuple[list[TakeProfitTarget], list[str]]:
    blockers: list[str] = []
    risk = stop.stop_loss_distance
    if risk <= 0:
        return [], ["Cannot compute targets with non-positive risk distance."]

    ref = entry.entry_reference_price
    raw: list[_TargetCand] = []

    for liq in liquidity_results:
        raw.extend(_liquidity_targets(liq, direction=direction, entry_price=ref))

    for struct in structure_results:
        raw.extend(_structure_targets(struct, direction=direction, entry_price=ref))

    if opposing_ob_fvg is not None:
        raw.extend(_opposing_zone_targets(opposing_ob_fvg, direction=direction, entry_price=ref))

    # Filter correct side of entry
    if direction == "bullish":
        raw = [t for t in raw if t.price > ref]
    else:
        raw = [t for t in raw if t.price < ref]

    if not raw:
        return [], ["No valid technical take-profit levels beyond entry."]

    # Sort toward progressive targets
    raw.sort(key=lambda t: t.price if direction == "bullish" else -t.price)
    deduped = _dedupe(raw, config.near_duplicate_pct)

    targets: list[TakeProfitTarget] = []
    for i, cand in enumerate(deduped):
        if len(targets) >= config.max_targets:
            break
        reward = abs(cand.price - ref)
        if reward <= 0:
            continue
        rr = reward / risk
        # Do not invent farther targets — skip sub-minimum for TP1 only by rejecting later
        if not targets and rr < config.minimum_primary_target_rr:
            # Skip this level; look for next technical level that meets min RR
            continue
        dist_pct = reward / ref * 100.0 if ref else 0.0
        idx = len(targets) + 1
        targets.append(
            TakeProfitTarget(
                index=idx,
                label=f"TP{idx}",
                price=cand.price,
                source=cand.source,
                source_event_key=cand.event_key,
                distance=reward,
                distance_pct=dist_pct,
                risk_reward_ratio=rr,
                explanation=cand.explanation,
            )
        )

    if not targets:
        blockers.append(
            f"No take-profit level meets minimum primary RR "
            f"{config.minimum_primary_target_rr}:1 without fabricating prices."
        )
        return [], blockers

    if targets[0].risk_reward_ratio < config.minimum_primary_target_rr:
        blockers.append(
            f"Primary target RR {targets[0].risk_reward_ratio:.3f} "
            f"< minimum {config.minimum_primary_target_rr}."
        )
        return [], blockers

    return targets, blockers


def _liquidity_targets(
    result: LiquidityResult,
    *,
    direction: str,
    entry_price: float,
) -> list[_TargetCand]:
    out: list[_TargetCand] = []
    levels = result.bsl_levels if direction == "bullish" else result.ssl_levels
    want = LiquidityType.BSL if direction == "bullish" else LiquidityType.SSL
    for lvl in levels:
        if lvl.liquidity_type != want:
            continue
        if lvl.status != LiquidityStatus.ACTIVE:
            continue
        if direction == "bullish" and lvl.price <= entry_price:
            continue
        if direction == "bearish" and lvl.price >= entry_price:
            continue
        out.append(
            _TargetCand(
                price=lvl.price,
                source=f"liquidity_{lvl.liquidity_type.value}",
                event_key=lvl.event_key,
                explanation=(
                    f"{lvl.timeframe.value} active {lvl.liquidity_type.value.upper()} "
                    f"at {lvl.price:.6g}."
                ),
            )
        )
    return out


def _structure_targets(
    result: MarketStructureResult,
    *,
    direction: str,
    entry_price: float,
) -> list[_TargetCand]:
    out: list[_TargetCand] = []
    kind = SwingKind.HIGH if direction == "bullish" else SwingKind.LOW
    for swing in result.swings:
        if not swing.confirmed or swing.kind != kind:
            continue
        if direction == "bullish" and swing.price <= entry_price:
            continue
        if direction == "bearish" and swing.price >= entry_price:
            continue
        out.append(
            _TargetCand(
                price=swing.price,
                source=f"confirmed_swing_{kind.value}",
                event_key=swing.event_key,
                explanation=(
                    f"{result.snapshot.timeframe.value} confirmed swing {kind.value} "
                    f"at {swing.price:.6g}."
                ),
            )
        )
    snap = result.snapshot
    if direction == "bullish" and snap.active_unbroken_swing_high is not None:
        p = snap.active_unbroken_swing_high
        if p > entry_price:
            out.append(
                _TargetCand(
                    price=p,
                    source="active_unbroken_swing_high",
                    event_key=None,
                    explanation=f"Active unbroken swing high at {p:.6g}.",
                )
            )
    if direction == "bearish" and snap.active_unbroken_swing_low is not None:
        p = snap.active_unbroken_swing_low
        if p < entry_price:
            out.append(
                _TargetCand(
                    price=p,
                    source="active_unbroken_swing_low",
                    event_key=None,
                    explanation=f"Active unbroken swing low at {p:.6g}.",
                )
            )
    return out


def _opposing_zone_targets(
    ob_fvg: ObFvgResult,
    *,
    direction: str,
    entry_price: float,
) -> list[_TargetCand]:
    """Opposing zones as magnet targets (bearish OB/FVG for longs, etc.)."""
    out: list[_TargetCand] = []
    if direction == "bullish":
        for ob in ob_fvg.bearish_order_blocks:
            if ob.status not in {ObStatus.ACTIVE, ObStatus.PARTIALLY_MITIGATED}:
                continue
            if not ob.confirmed:
                continue
            # Use zone_low as first touch of opposing supply
            if ob.zone_low > entry_price:
                out.append(
                    _TargetCand(
                        price=ob.zone_low,
                        source="opposing_bearish_ob",
                        event_key=ob.event_key,
                        explanation=(
                            f"Opposing bearish OB low {ob.zone_low:.6g} "
                            f"({ob.status.value})."
                        ),
                    )
                )
        for fvg in ob_fvg.bearish_fvgs:
            if fvg.status not in {FvgStatus.ACTIVE, FvgStatus.PARTIALLY_FILLED}:
                continue
            if not fvg.confirmed:
                continue
            if fvg.zone_low > entry_price:
                out.append(
                    _TargetCand(
                        price=fvg.zone_low,
                        source="opposing_bearish_fvg",
                        event_key=fvg.event_key,
                        explanation=(
                            f"Opposing bearish FVG low {fvg.zone_low:.6g} "
                            f"({fvg.status.value})."
                        ),
                    )
                )
    else:
        for ob in ob_fvg.bullish_order_blocks:
            if ob.status not in {ObStatus.ACTIVE, ObStatus.PARTIALLY_MITIGATED}:
                continue
            if not ob.confirmed:
                continue
            if ob.zone_high < entry_price:
                out.append(
                    _TargetCand(
                        price=ob.zone_high,
                        source="opposing_bullish_ob",
                        event_key=ob.event_key,
                        explanation=(
                            f"Opposing bullish OB high {ob.zone_high:.6g} "
                            f"({ob.status.value})."
                        ),
                    )
                )
        for fvg in ob_fvg.bullish_fvgs:
            if fvg.status not in {FvgStatus.ACTIVE, FvgStatus.PARTIALLY_FILLED}:
                continue
            if not fvg.confirmed:
                continue
            if fvg.zone_high < entry_price:
                out.append(
                    _TargetCand(
                        price=fvg.zone_high,
                        source="opposing_bullish_fvg",
                        event_key=fvg.event_key,
                        explanation=(
                            f"Opposing bullish FVG high {fvg.zone_high:.6g} "
                            f"({fvg.status.value})."
                        ),
                    )
                )
    return out


def _dedupe(items: list[_TargetCand], near_pct: float) -> list[_TargetCand]:
    out: list[_TargetCand] = []
    for item in items:
        if any(abs(item.price - kept.price) / kept.price <= near_pct for kept in out if kept.price):
            continue
        out.append(item)
    return out
