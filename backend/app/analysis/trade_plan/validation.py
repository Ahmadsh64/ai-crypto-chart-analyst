"""Trade-plan validation layer (Phase 4.3)."""

from __future__ import annotations

from app.analysis.trade_plan.config import TradePlanConfig
from app.analysis.trade_plan.models import (
    EligibilityResult,
    EntryZone,
    PositionSizing,
    RiskMetrics,
    StopLossPlan,
    TakeProfitTarget,
    ValidationResult,
)
from app.exchanges.types import MarketType


def validate_plan(
    *,
    eligibility: EligibilityResult,
    direction: str | None,
    entry: EntryZone | None,
    stop: StopLossPlan | None,
    targets: list[TakeProfitTarget],
    risk: RiskMetrics | None,
    sizing: PositionSizing | None,
    market_type: MarketType,
    config: TradePlanConfig,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    blocking: list[str] = []

    if not eligibility.is_eligible:
        blocking.extend(eligibility.blocking_reasons)
        return ValidationResult(
            is_valid=False,
            validation_errors=list(eligibility.blocking_reasons),
            warnings=warnings,
            blocking_reasons=blocking,
        )

    if direction not in {"bullish", "bearish"}:
        blocking.append("Plan direction missing.")
    if entry is None:
        blocking.append("Entry zone missing.")
    if stop is None:
        blocking.append("Stop loss missing.")
    if not targets:
        blocking.append("No valid take-profit targets.")
    if risk is None:
        blocking.append("Risk metrics missing.")

    if entry is not None:
        if entry.entry_low >= entry.entry_high:
            errors.append("Entry low must be < entry high.")
        if not _finite(entry.entry_reference_price):
            errors.append("Entry reference price is not finite.")
        if not (
            entry.entry_low - 1e-12
            <= entry.entry_reference_price
            <= entry.entry_high + 1e-12
        ):
            # Allow tiny float noise; market-condition should be inside
            if entry.entry_type != "structure_retest":
                warnings.append("Entry reference sits outside declared zone bounds.")

    if entry is not None and stop is not None and direction == "bullish":
        if stop.stop_loss_price >= entry.entry_reference_price:
            errors.append("Long stop must be below entry reference.")
        if stop.stop_loss_distance <= 0:
            errors.append("Stop-loss distance must be positive.")
    if entry is not None and stop is not None and direction == "bearish":
        if stop.stop_loss_price <= entry.entry_reference_price:
            errors.append("Short stop must be above entry reference.")
        if stop.stop_loss_distance <= 0:
            errors.append("Stop-loss distance must be positive.")

    prev = None
    for t in targets:
        if direction == "bullish" and entry is not None and t.price <= entry.entry_reference_price:
            errors.append(f"{t.label} is not above entry.")
        if direction == "bearish" and entry is not None and t.price >= entry.entry_reference_price:
            errors.append(f"{t.label} is not below entry.")
        if t.risk_reward_ratio != t.risk_reward_ratio or t.risk_reward_ratio <= 0:
            errors.append(f"{t.label} RR is not a positive finite value.")
        if prev is not None:
            if direction == "bullish" and t.price <= prev:
                errors.append("Take-profit targets are not ascending for bullish plan.")
            if direction == "bearish" and t.price >= prev:
                errors.append("Take-profit targets are not descending for bearish plan.")
        prev = t.price

    if risk is not None and not risk.meets_minimum_rr:
        errors.append(
            f"Primary RR {risk.primary_rr} below minimum {risk.minimum_required_rr}."
        )

    if sizing is not None and not sizing.sizing_available:
        warnings.append(sizing.sizing_explanation)
    if market_type == MarketType.SPOT and direction == "bearish":
        warnings.append(
            "Spot market: bearish plan is a hypothetical downside scenario; "
            "a short position cannot be executed as a standard Spot trade."
        )

    blocking.extend(errors)
    # Dedup
    blocking = _unique(blocking)
    errors = _unique(errors)
    warnings = _unique(warnings)

    return ValidationResult(
        is_valid=len(blocking) == 0,
        validation_errors=errors,
        warnings=warnings,
        blocking_reasons=blocking,
    )


def _finite(value: float) -> bool:
    return value == value and abs(value) != float("inf")


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out
