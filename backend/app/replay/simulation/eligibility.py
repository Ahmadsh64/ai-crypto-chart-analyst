"""Trade eligibility from historical analysis snapshots (Phase 5.2.2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.exchanges.types import MarketType
from app.replay.analysis.models import HistoricalAnalysisSnapshot
from app.replay.simulation.config import SimulationConfig
from app.replay.simulation.enums import EntryPricePolicy, TradeDirection
from app.replay.timeline import ensure_utc


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    direction: TradeDirection | None = None
    entry_limit_price: float | None = None
    stop_loss: float | None = None
    take_profits: tuple[float, ...] = ()
    quantity: float | None = None
    expires_at: datetime | None = None
    signal_key: str = ""
    rejection_reason: str | None = None


def derive_entry_limit_price(
    entry_zone: dict[str, Any] | None,
    *,
    direction: TradeDirection,
    policy: EntryPricePolicy,
) -> float | None:
    """Derive limit price from Phase 4.3 entry zone using explicit policy."""
    if not entry_zone:
        return None
    ref = entry_zone.get("entry_reference_price")
    low = entry_zone.get("entry_low")
    high = entry_zone.get("entry_high")
    try:
        if policy == "exact_reference_price":
            if ref is None:
                return None
            return float(ref)
        if policy == "zone_midpoint":
            if low is None or high is None:
                return float(ref) if ref is not None else None
            return (float(low) + float(high)) / 2.0
        if policy == "zone_boundary":
            if direction == "LONG":
                # Conservative: buy at the lower (cheaper) boundary of the zone
                if low is not None:
                    return float(low)
            else:
                if high is not None:
                    return float(high)
            return float(ref) if ref is not None else None
    except (TypeError, ValueError):
        return None
    return None


def build_signal_key(snap: HistoricalAnalysisSnapshot, direction: TradeDirection) -> str:
    ts = ensure_utc(snap.replay_timestamp).isoformat()
    did = snap.decision_id or "nodec"
    plan = snap.trade_plan_id or "noplan"
    return (
        f"{snap.session_id}|{did}|{plan}|{ts}|{snap.exchange.value}|"
        f"{snap.market_type.value}|{snap.symbol}|{direction}"
    )


def evaluate_eligibility(
    snap: HistoricalAnalysisSnapshot,
    *,
    config: SimulationConfig,
) -> EligibilityResult:
    """Only LONG/SHORT with a complete executable plan become eligible."""
    decision = str(snap.decision).upper().replace("_", " ").strip()
    if decision not in {"LONG", "SHORT"}:
        return EligibilityResult(
            eligible=False,
            rejection_reason=f"Decision {snap.decision!r} is not executable.",
        )

    direction: TradeDirection = "LONG" if decision == "LONG" else "SHORT"
    signal_key = build_signal_key(snap, direction)

    if snap.market_type == MarketType.SPOT and direction == "SHORT":
        return EligibilityResult(
            eligible=False,
            direction=direction,
            signal_key=signal_key,
            rejection_reason="Spot must never open SHORT trades.",
        )

    lifecycle = str(snap.lifecycle_status or "").lower()
    if lifecycle in {"expired", "invalidated"}:
        return EligibilityResult(
            eligible=False,
            direction=direction,
            signal_key=signal_key,
            rejection_reason=f"Setup lifecycle is {lifecycle}.",
        )

    if snap.trade_plan_status and str(snap.trade_plan_status).lower() not in {
        "eligible",
        "planstatus.eligible",
    }:
        status = str(snap.trade_plan_status).lower()
        if "eligible" not in status:
            return EligibilityResult(
                eligible=False,
                direction=direction,
                signal_key=signal_key,
                rejection_reason=f"Trade plan status is {snap.trade_plan_status!r}.",
            )

    if not snap.entry_zone:
        return EligibilityResult(
            eligible=False,
            direction=direction,
            signal_key=signal_key,
            rejection_reason="Missing entry zone.",
        )

    entry_limit = derive_entry_limit_price(
        snap.entry_zone,
        direction=direction,
        policy=config.entry_price_policy,
    )
    if entry_limit is None or entry_limit <= 0:
        return EligibilityResult(
            eligible=False,
            direction=direction,
            signal_key=signal_key,
            rejection_reason=(
                f"Cannot derive entry price with policy {config.entry_price_policy!r}."
            ),
        )

    if snap.stop_loss is None or snap.stop_loss <= 0:
        return EligibilityResult(
            eligible=False,
            direction=direction,
            signal_key=signal_key,
            rejection_reason="Missing or invalid stop loss.",
        )

    tps = [float(p) for p in snap.take_profit_levels if p is not None and float(p) > 0]
    if not tps:
        return EligibilityResult(
            eligible=False,
            direction=direction,
            signal_key=signal_key,
            rejection_reason="Missing valid take-profit configuration.",
        )

    if direction == "LONG":
        if snap.stop_loss >= entry_limit:
            return EligibilityResult(
                eligible=False,
                direction=direction,
                signal_key=signal_key,
                rejection_reason="LONG stop loss must be below entry.",
            )
        if any(tp <= entry_limit for tp in tps):
            return EligibilityResult(
                eligible=False,
                direction=direction,
                signal_key=signal_key,
                rejection_reason="LONG take profits must be above entry.",
            )
    else:
        if snap.stop_loss <= entry_limit:
            return EligibilityResult(
                eligible=False,
                direction=direction,
                signal_key=signal_key,
                rejection_reason="SHORT stop loss must be above entry.",
            )
        if any(tp >= entry_limit for tp in tps):
            return EligibilityResult(
                eligible=False,
                direction=direction,
                signal_key=signal_key,
                rejection_reason="SHORT take profits must be below entry.",
            )

    if snap.risk_reward is not None and snap.risk_reward <= 0:
        return EligibilityResult(
            eligible=False,
            direction=direction,
            signal_key=signal_key,
            rejection_reason="Invalid risk/reward.",
        )

    qty = snap.position_size
    if qty is None or float(qty) <= 0:
        return EligibilityResult(
            eligible=False,
            direction=direction,
            signal_key=signal_key,
            rejection_reason="Missing valid position size (no invented balance).",
        )

    if not snap.data_ready and snap.data_quality in {"empty", "insufficient", "unavailable"}:
        return EligibilityResult(
            eligible=False,
            direction=direction,
            signal_key=signal_key,
            rejection_reason=f"Insufficient market data ({snap.data_quality}).",
        )

    if snap.analysis_error:
        return EligibilityResult(
            eligible=False,
            direction=direction,
            signal_key=signal_key,
            rejection_reason=f"Analysis error: {snap.analysis_error}",
        )

    return EligibilityResult(
        eligible=True,
        direction=direction,
        entry_limit_price=float(entry_limit),
        stop_loss=float(snap.stop_loss),
        take_profits=tuple(tps),
        quantity=float(qty),
        expires_at=ensure_utc(snap.expires_at) if snap.expires_at else None,
        signal_key=signal_key,
    )
