"""Execution-timeframe matrix overlays (Phase 5.5 Step 1).

Config overlays only — does not change confluence weights, RR formulas,
or Decision/Trade Plan eligibility thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.analysis.decision_engine.config import DEFAULT_DECISION_CONFIG, DecisionConfig
from app.analysis.multi_timeframe.config import MTF_LADDER
from app.analysis.trade_plan.config import DEFAULT_TRADE_PLAN_CONFIG, TradePlanConfig
from app.exchanges.types import ExchangeId, MarketType, Timeframe

# Product-approved execution timeframes (independent opportunities each).
EXECUTION_TIMEFRAMES: tuple[Timeframe, ...] = (
    Timeframe.M5,
    Timeframe.M15,
    Timeframe.H1,
    Timeframe.H4,
)

# Full ladder must always be loaded for MTF context (never omit HTF).
REQUIRED_MTF_LADDER: tuple[Timeframe, ...] = tuple(MTF_LADDER)


@dataclass(frozen=True)
class ExecutionTimeframeOverlay:
    """Setup / confirmation role mapping for one execution timeframe."""

    execution_timeframe: Timeframe
    setup_timeframe: Timeframe
    confirmation_timeframe: Timeframe
    liquidity_timeframes: tuple[Timeframe, ...]


# Setup = structure TF for the plan; confirmation = next-lower ladder TF.
# Thresholds (min score, RR, require confirmation flag) stay at engine defaults.
_OVERLAYS: dict[Timeframe, ExecutionTimeframeOverlay] = {
    Timeframe.M5: ExecutionTimeframeOverlay(
        execution_timeframe=Timeframe.M5,
        setup_timeframe=Timeframe.M5,
        confirmation_timeframe=Timeframe.M5,
        liquidity_timeframes=(Timeframe.M15, Timeframe.M5),
    ),
    Timeframe.M15: ExecutionTimeframeOverlay(
        execution_timeframe=Timeframe.M15,
        setup_timeframe=Timeframe.M15,
        confirmation_timeframe=Timeframe.M5,
        liquidity_timeframes=(Timeframe.H1, Timeframe.M15),
    ),
    Timeframe.H1: ExecutionTimeframeOverlay(
        execution_timeframe=Timeframe.H1,
        setup_timeframe=Timeframe.H1,
        confirmation_timeframe=Timeframe.M15,
        liquidity_timeframes=(Timeframe.H4, Timeframe.H1),
    ),
    Timeframe.H4: ExecutionTimeframeOverlay(
        execution_timeframe=Timeframe.H4,
        setup_timeframe=Timeframe.H4,
        confirmation_timeframe=Timeframe.H1,
        liquidity_timeframes=(Timeframe.H4, Timeframe.H1),
    ),
}


def get_execution_overlay(execution_timeframe: Timeframe) -> ExecutionTimeframeOverlay:
    if execution_timeframe not in _OVERLAYS:
        raise ValueError(f"Unsupported execution timeframe: {execution_timeframe}")
    return _OVERLAYS[execution_timeframe]


def decision_config_for_execution(execution_timeframe: Timeframe) -> DecisionConfig:
    """Clone default DecisionConfig with setup/confirm TF overlay only."""
    overlay = get_execution_overlay(execution_timeframe)
    return DEFAULT_DECISION_CONFIG.model_copy(
        update={
            "setup_timeframe": overlay.setup_timeframe,
            "confirmation_timeframe": overlay.confirmation_timeframe,
            # Always require full MTF ladder readiness — never drop HTF.
            "required_timeframes": REQUIRED_MTF_LADDER,
            # Do not weaken confirmation gate.
            "require_5m_confirmation": DEFAULT_DECISION_CONFIG.require_5m_confirmation,
            "min_directional_score": DEFAULT_DECISION_CONFIG.min_directional_score,
            "min_score_margin": DEFAULT_DECISION_CONFIG.min_score_margin,
            "minimum_primary_rr": DEFAULT_DECISION_CONFIG.minimum_primary_rr,
            "require_assessment_strength": DEFAULT_DECISION_CONFIG.require_assessment_strength,
            "block_critical_conflicts": DEFAULT_DECISION_CONFIG.block_critical_conflicts,
        }
    )


def trade_plan_config_for_execution(execution_timeframe: Timeframe) -> TradePlanConfig:
    """Clone default TradePlanConfig with setup/confirm/liquidity TF overlay only."""
    overlay = get_execution_overlay(execution_timeframe)
    # Trade plan historically required H4/H1/M15; keep those plus M5 so ladder stays intact.
    required = tuple(dict.fromkeys((*REQUIRED_MTF_LADDER,)))
    return DEFAULT_TRADE_PLAN_CONFIG.model_copy(
        update={
            "setup_timeframe": overlay.setup_timeframe,
            "confirmation_timeframe": overlay.confirmation_timeframe,
            "liquidity_timeframes": overlay.liquidity_timeframes,
            "required_timeframes": required,
            "min_directional_score": DEFAULT_TRADE_PLAN_CONFIG.min_directional_score,
            "min_score_margin": DEFAULT_TRADE_PLAN_CONFIG.min_score_margin,
            "minimum_primary_target_rr": DEFAULT_TRADE_PLAN_CONFIG.minimum_primary_target_rr,
            "require_assessment_strength": DEFAULT_TRADE_PLAN_CONFIG.require_assessment_strength,
            "block_critical_conflicts": DEFAULT_TRADE_PLAN_CONFIG.block_critical_conflicts,
        }
    )


def opportunity_id_for(
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    execution_timeframe: Timeframe,
) -> str:
    """
    Slot-level key (legacy helper). Prefer app.scanner.identity for persistence ids.
    """
    from app.scanner.identity import compute_slot_key

    return compute_slot_key(exchange, market_type, symbol, execution_timeframe)
