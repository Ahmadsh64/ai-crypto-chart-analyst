"""Explicit decision priority rules (Phase 4.4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.analysis.decision_engine.config import DecisionConfig, FinalDecision, SetupLifecycle
from app.analysis.decision_engine.models import (
    DecisionEligibilityResult,
    EntryConfirmationResult,
)
from app.analysis.trade_plan.models import TradePlanResult
from app.exchanges.types import Candle, MarketType


def resolve_decision(
    *,
    eligibility: DecisionEligibilityResult,
    confirmation: EntryConfirmationResult,
    trade_plan: TradePlanResult,
    market_type: MarketType,
    current_price: float | None,
    price_inside_zone: bool,
    setup_expired: bool,
    setup_invalidated: bool,
    both_directions_valid: bool,
    config: DecisionConfig,
) -> tuple[FinalDecision, SetupLifecycle, str, list[str]]:
    """
    Priority (documented):
    1. Invalid/unavailable data / critical blockers → NO TRADE
    2. Critical conflict / invalid plan (via eligibility) → NO TRADE
    3. Expired / invalidated setup → NO TRADE
    4. Insufficient confluence (via eligibility) → NO TRADE
    5. Both directions valid → NO TRADE
    6. Valid setup, no entry confirmation or price outside zone → WAIT
    7. Valid setup + confirmation + price in zone → LONG/SHORT (Spot short restricted)
    """
    blocking: list[str] = []

    if both_directions_valid:
        return (
            "NO TRADE",
            "invalidated",
            "NO TRADE: Bullish and bearish conditions both appear valid; "
            "ambiguous dual-direction setups are not resolved by score alone.",
            ["Ambiguous dual-direction validity."],
        )

    if setup_expired:
        return (
            "NO TRADE",
            "expired",
            "NO TRADE: The analytical setup has expired beyond the configured age limit.",
            ["Setup expired."],
        )

    if setup_invalidated:
        return (
            "NO TRADE",
            "invalidated",
            "NO TRADE: The setup has been invalidated (stop/structure breach or plan invalid).",
            ["Setup invalidated."],
        )

    if not eligibility.is_setup_valid:
        reasons = eligibility.blocking_reasons or ["Setup is not valid."]
        # Distinguish data/conflict vs weak confluence for messaging
        reason = "NO TRADE: " + "; ".join(reasons[:3])
        lifecycle: SetupLifecycle = "invalidated"
        if any("stale" in r.lower() or "unavailable" in r.lower() or "missing" in r.lower() for r in reasons):
            lifecycle = "invalidated"
        return "NO TRADE", lifecycle, reason, list(reasons)

    direction = eligibility.direction
    assert direction is not None

    # Spot SHORT restriction
    if (
        market_type == MarketType.SPOT
        and direction == "bearish"
        and not config.spot_allow_short
    ):
        # Still allow WAIT while awaiting confirmation so the hypothetical plan is visible;
        # once entry would otherwise confirm → NO TRADE (not SHORT).
        if confirmation.is_confirmed and price_inside_zone:
            msg = (
                "NO TRADE: Bearish confluence and entry confirmation are present, but a "
                "short position cannot be opened as a standard Spot trade. "
                "The hypothetical downside plan remains analytical only."
            )
            return "NO TRADE", "invalidated", msg, [
                "Spot market does not support executable SHORT decisions."
            ]

    entry_ready = confirmation.is_confirmed
    if config.require_5m_confirmation and not entry_ready:
        return (
            "WAIT",
            "awaiting_confirmation",
            (
                f"WAIT: {direction.capitalize()} confluence is strong and the hypothetical "
                f"trade plan is valid. However, the 5M entry confirmation has not occurred. "
                f"{confirmation.explanation}"
            ),
            list(confirmation.blocking_reasons),
        )

    if config.require_price_inside_entry_zone and not price_inside_zone:
        return (
            "WAIT",
            "awaiting_confirmation",
            (
                f"WAIT: {direction.capitalize()} setup remains valid, but the current price "
                f"is outside the planned entry zone"
                + (f" ({current_price})" if current_price is not None else "")
                + ". No analytical entry trigger is currently confirmed."
            ),
            ["Current price outside entry zone."],
        )

    if direction == "bullish":
        if market_type == MarketType.SPOT and not config.spot_allow_long:
            return (
                "NO TRADE",
                "invalidated",
                "NO TRADE: Spot LONG decisions are disabled by configuration.",
                ["Spot LONG disabled."],
            )
        return (
            "LONG",
            "entry_confirmed",
            (
                "LONG: Strong bullish confluence, eligible trade plan, price inside the "
                f"entry zone, and 5M confirmation ({confirmation.confirmation_type}). "
                "Analytical conditions are satisfied — no order is executed."
            ),
            [],
        )

    # bearish → SHORT (futures / when allowed)
    return (
        "SHORT",
        "entry_confirmed",
        (
            "SHORT: Strong bearish confluence, eligible trade plan, price inside the "
            f"entry zone, and 5M confirmation ({confirmation.confirmation_type}). "
            "Analytical conditions are satisfied — no order is executed."
        ),
        [],
    )


def is_setup_expired(
    *,
    trade_plan: TradePlanResult,
    setup_candles: list[Candle],
    as_of: datetime,
    config: DecisionConfig,
) -> bool:
    if trade_plan.entry is None:
        return False
    # Prefer source from entry; fall back to analysis timestamp
    # Entry has no timestamp field — use trade_plan.analysis_timestamp as setup clock
    # and count closed setup-TF candles after entry reference existence.
    closed = [c for c in setup_candles if c.is_closed]
    if not closed:
        return False
    start = trade_plan.analysis_timestamp
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    age_hours = (as_of - start).total_seconds() / 3600.0
    if age_hours > config.max_setup_age_hours:
        return True
    after = [c for c in closed if c.timestamp >= start]
    # When plan was just computed, after may be empty/short — not expired
    if len(after) > config.max_setup_age_candles:
        return True
    return False


def is_setup_invalidated(
    *,
    trade_plan: TradePlanResult,
    current_price: float | None,
) -> bool:
    if trade_plan.plan_status in {"blocked", "invalid"}:
        return True
    if current_price is None or trade_plan.stop_loss is None or trade_plan.direction is None:
        return False
    sl = trade_plan.stop_loss.stop_loss_price
    if trade_plan.direction == "bullish" and current_price <= sl:
        return True
    if trade_plan.direction == "bearish" and current_price >= sl:
        return True
    return False


def expires_at(as_of: datetime, config: DecisionConfig) -> datetime:
    return as_of + timedelta(hours=config.max_setup_age_hours)
