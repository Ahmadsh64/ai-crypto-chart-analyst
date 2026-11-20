"""Immutable analysis snapshot for AI explainer grounding."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.api.schemas.decision import DecisionResponse
from app.api.schemas.trade_plan import TradePlanResponse


class AnalysisSnapshot(BaseModel):
    """Validated deterministic snapshot — AI may describe but never mutate."""

    exchange: str
    symbol: str
    market_type: str
    analysis_timestamp: str
    data_freshness: str
    decision: str
    decision_reason: str
    lifecycle: str | None = None
    direction: str | None = None
    confluence_bullish: float | None = None
    confluence_bearish: float | None = None
    preliminary_assessment: str | None = None
    conflicts: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    blocking_conditions: list[str] = Field(default_factory=list)
    trade_plan_status: str | None = None
    plan_id: str | None = None
    decision_id: str | None = None
    entry_reference_price: float | None = None
    entry_low: float | None = None
    entry_high: float | None = None
    stop_loss_price: float | None = None
    take_profit_prices: list[float] = Field(default_factory=list)
    primary_rr: float | None = None
    price_inside_entry_zone: bool | None = None
    spot_restriction: str | None = None
    analysis_only_disclaimer: str = (
        "Analysis only — no orders are executed."
    )
    raw_decision: dict[str, Any] = Field(default_factory=dict)
    raw_trade_plan: dict[str, Any] = Field(default_factory=dict)


def build_analysis_snapshot(
    decision: DecisionResponse,
    trade_plan: TradePlanResponse | None,
    *,
    data_freshness: str = "UNKNOWN",
) -> AnalysisSnapshot:
    entry_ref = None
    entry_low = None
    entry_high = None
    if decision.entry_zone_summary:
        ez = decision.entry_zone_summary
        entry_ref = _f(ez.get("entry_reference_price"))
        entry_low = _f(ez.get("entry_low"))
        entry_high = _f(ez.get("entry_high"))
    if trade_plan and trade_plan.entry:
        entry_ref = entry_ref if entry_ref is not None else trade_plan.entry.entry_reference_price
        entry_low = entry_low if entry_low is not None else trade_plan.entry.entry_low
        entry_high = entry_high if entry_high is not None else trade_plan.entry.entry_high

    sl = decision.stop_loss_price
    if sl is None and trade_plan and trade_plan.stop_loss:
        sl = trade_plan.stop_loss.stop_loss_price

    tps = list(decision.take_profit_prices or [])
    if not tps and trade_plan:
        tps = [t.price for t in trade_plan.take_profit_targets]

    rr = decision.primary_rr
    if rr is None and trade_plan and trade_plan.risk:
        rr = trade_plan.risk.primary_rr

    scores = decision.confluence_scores
    return AnalysisSnapshot(
        exchange=str(decision.exchange.value if hasattr(decision.exchange, "value") else decision.exchange),
        symbol=decision.symbol,
        market_type=str(
            decision.market_type.value
            if hasattr(decision.market_type, "value")
            else decision.market_type
        ),
        analysis_timestamp=(
            decision.analysis_timestamp.isoformat()
            if hasattr(decision.analysis_timestamp, "isoformat")
            else str(decision.analysis_timestamp)
        ),
        data_freshness=data_freshness,
        decision=str(decision.decision),
        decision_reason=decision.decision_reason,
        lifecycle=str(decision.lifecycle) if decision.lifecycle else None,
        direction=str(decision.direction) if decision.direction else None,
        confluence_bullish=scores.bullish_score if scores else None,
        confluence_bearish=scores.bearish_score if scores else None,
        preliminary_assessment=scores.preliminary_assessment if scores else None,
        conflicts=list(decision.conflict_ids or []),
        supporting_evidence=list(decision.supporting_evidence or []),
        blocking_conditions=list(decision.blocking_conditions or []),
        trade_plan_status=decision.trade_plan_status
        or (trade_plan.plan_status if trade_plan else None),
        plan_id=trade_plan.plan_id if trade_plan else decision.trade_plan_id,
        decision_id=decision.decision_id,
        entry_reference_price=entry_ref,
        entry_low=entry_low,
        entry_high=entry_high,
        stop_loss_price=sl,
        take_profit_prices=tps,
        primary_rr=rr,
        price_inside_entry_zone=decision.price_inside_entry_zone,
        spot_restriction=decision.spot_restriction,
        analysis_only_disclaimer=decision.analysis_only_disclaimer,
        raw_decision=decision.model_dump(mode="json"),
        raw_trade_plan=trade_plan.model_dump(mode="json") if trade_plan else {},
    )


def _f(v: Any) -> float | None:
    try:
        if v is None:
            return None
        n = float(v)
        return n if n == n else None  # noqa: PLR0124
    except (TypeError, ValueError):
        return None
