"""Map existing Decision/Trade Plan outputs to opportunity status (no new rules)."""

from __future__ import annotations

from app.analysis.decision_engine.models import DecisionResult
from app.analysis.trade_plan.models import TradePlanResult
from app.scanner.config import ScannerConfig
from app.scanner.models import OpportunityStatus


def _entry_bounds(plan: TradePlanResult | None) -> tuple[float | None, float | None, float | None]:
    if plan is None or plan.entry is None:
        return None, None, None
    e = plan.entry
    return e.entry_low, e.entry_high, e.entry_reference_price


def entry_distance_pct(
    price: float | None,
    entry_low: float | None,
    entry_high: float | None,
    entry_ref: float | None,
) -> float | None:
    if price is None or not (price > 0):
        return None
    if entry_low is not None and entry_high is not None and entry_low <= entry_high:
        if entry_low <= price <= entry_high:
            return 0.0
        if price < entry_low:
            return abs(price - entry_low) / price * 100.0
        return abs(price - entry_high) / price * 100.0
    if entry_ref is not None and entry_ref > 0:
        return abs(price - entry_ref) / price * 100.0
    return None


def classify_opportunity_status(
    *,
    decision: DecisionResult | None,
    trade_plan: TradePlanResult | None,
    current_price: float | None,
    config: ScannerConfig,
    data_ok: bool,
) -> OpportunityStatus:
    """Status mapping only — does not invent LONG/SHORT eligibility."""
    if not data_ok or decision is None:
        return OpportunityStatus.DATA_UNAVAILABLE

    lifecycle = decision.lifecycle
    if lifecycle == "invalidated":
        return OpportunityStatus.INVALIDATED
    if lifecycle == "expired":
        return OpportunityStatus.EXPIRED

    if decision.decision in ("WAIT", "NO TRADE"):
        if lifecycle in ("setup_detected", "awaiting_confirmation"):
            return OpportunityStatus.WAITING
        if decision.decision == "NO TRADE" and lifecycle == "invalidated":
            return OpportunityStatus.INVALIDATED
        return OpportunityStatus.WAITING

    # LONG / SHORT from existing Decision Engine
    plan_ok = (
        trade_plan is not None
        and trade_plan.plan_status == "eligible"
        and trade_plan.entry is not None
        and trade_plan.stop_loss is not None
    )
    if not plan_ok:
        return OpportunityStatus.WAITING

    low, high, ref = _entry_bounds(trade_plan)
    dist = entry_distance_pct(current_price, low, high, ref)
    confirmed = bool(decision.entry_confirmation and decision.entry_confirmation.is_confirmed)
    inside = bool(decision.price_inside_entry_zone)

    if confirmed or inside or (dist is not None and dist <= 0.0):
        return OpportunityStatus.READY

    if dist is not None and dist <= config.approaching_entry_pct:
        return OpportunityStatus.APPROACHING_ENTRY

    if lifecycle == "awaiting_confirmation":
        return OpportunityStatus.APPROACHING_ENTRY

    return OpportunityStatus.WAITING


def is_actionable(status: OpportunityStatus) -> bool:
    return status == OpportunityStatus.READY
