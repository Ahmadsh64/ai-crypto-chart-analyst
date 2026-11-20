"""Risk/reward and hypothetical position sizing (Phase 4.3)."""

from __future__ import annotations

from app.analysis.trade_plan.config import TradePlanConfig
from app.analysis.trade_plan.models import (
    EntryZone,
    PositionSizing,
    RiskMetrics,
    StopLossPlan,
    TakeProfitTarget,
)
from app.exchanges.types import MarketType


def calculate_risk_metrics(
    *,
    direction: str,
    entry: EntryZone,
    stop: StopLossPlan,
    targets: list[TakeProfitTarget],
    config: TradePlanConfig,
) -> RiskMetrics:
    ref = entry.entry_reference_price
    if direction == "bullish":
        risk = ref - stop.stop_loss_price
    else:
        risk = stop.stop_loss_price - ref
    risk = abs(risk) if risk == risk else 0.0
    rewards = [t.distance for t in targets]
    primary_rr = targets[0].risk_reward_ratio if targets else None
    return RiskMetrics(
        risk_distance=risk,
        risk_distance_pct=(risk / ref * 100.0) if ref else 0.0,
        reward_distances=rewards,
        primary_rr=primary_rr,
        minimum_required_rr=config.minimum_primary_target_rr,
        meets_minimum_rr=bool(
            primary_rr is not None and primary_rr >= config.minimum_primary_target_rr
        ),
    )


def calculate_position_sizing(
    *,
    entry: EntryZone,
    stop: StopLossPlan,
    account_balance: float,
    risk_percent: float,
    market_type: MarketType,
    config: TradePlanConfig,
    contract_multiplier: float | None = None,
) -> PositionSizing:
    warnings: list[str] = []
    risk_amount = account_balance * (risk_percent / 100.0)
    risk_distance = abs(entry.entry_reference_price - stop.stop_loss_price)

    if risk_distance <= 0 or risk_amount <= 0:
        return PositionSizing(
            account_balance=account_balance,
            risk_percent=risk_percent,
            risk_amount=risk_amount,
            position_size=None,
            position_notional=None,
            estimated_loss_at_sl=None,
            contract_multiplier=None,
            sizing_available=False,
            sizing_explanation="Sizing unavailable: non-positive risk distance or risk amount.",
            is_hypothetical=True,
        )

    mult = contract_multiplier if contract_multiplier is not None else config.contract_multiplier
    # Without instrument metadata we only support a linear base-asset model (mult=1).
    # Futures contract specs are not fetched — mark unavailable if caller passes None explicitly
    # requesting metadata. Default path uses mult=1 with clear hypothetical labeling.
    if mult is None or mult <= 0:
        return PositionSizing(
            account_balance=account_balance,
            risk_percent=risk_percent,
            risk_amount=risk_amount,
            position_size=None,
            position_notional=None,
            estimated_loss_at_sl=None,
            contract_multiplier=None,
            sizing_available=False,
            sizing_explanation=(
                "Sizing unavailable: required contract multiplier metadata is missing."
            ),
            is_hypothetical=True,
        )

    # quantity in base asset such that loss at SL ≈ risk_amount
    # loss ≈ position_size * risk_distance * mult
    position_size = risk_amount / (risk_distance * mult)
    notional = position_size * entry.entry_reference_price * mult
    estimated_loss = position_size * risk_distance * mult

    venue_note = (
        "Linear base-asset hypothetical sizing (multiplier=1). "
        "Fees, funding and slippage are not modeled."
    )
    if market_type == MarketType.SPOT:
        venue_note += " Spot sizing assumes long inventory; short Spot is not executable."
    else:
        venue_note += " Futures sizing is hypothetical and does not recommend leverage."

    return PositionSizing(
        account_balance=account_balance,
        risk_percent=risk_percent,
        risk_amount=risk_amount,
        position_size=position_size,
        position_notional=notional,
        estimated_loss_at_sl=estimated_loss,
        contract_multiplier=mult,
        sizing_available=True,
        sizing_explanation=venue_note,
        is_hypothetical=True,
    )


def risk_reward(
    *,
    direction: str,
    entry_price: float,
    stop_price: float,
    target_price: float,
) -> float:
    if direction == "bullish":
        risk = entry_price - stop_price
        reward = target_price - entry_price
    else:
        risk = stop_price - entry_price
        reward = entry_price - target_price
    if risk <= 0 or reward <= 0:
        return float("nan")
    return reward / risk
