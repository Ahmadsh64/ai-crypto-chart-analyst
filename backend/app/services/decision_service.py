"""REST service for final trading decisions (Phase 4.4)."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException

from app.analysis.decision_engine import analyze_decision
from app.analysis.decision_engine.config import DEFAULT_DECISION_CONFIG, DecisionConfig
from app.analysis.trade_plan import analyze_trade_plan
from app.analysis.trade_plan.config import DEFAULT_TRADE_PLAN_CONFIG, TradePlanConfig
from app.api.schemas.decision import DecisionResponse
from app.exchanges.types import ExchangeId, MarketType
from app.services.analysis_context import build_analysis_context


def _validate_sizing(
    account_balance: float | None,
    risk_percent: float | None,
    plan_cfg: TradePlanConfig,
) -> tuple[float, float]:
    balance = (
        float(account_balance)
        if account_balance is not None
        else plan_cfg.default_account_balance
    )
    risk = (
        float(risk_percent) if risk_percent is not None else plan_cfg.default_risk_percent
    )
    if balance < plan_cfg.min_account_balance:
        raise HTTPException(
            status_code=422,
            detail=f"account_balance must be >= {plan_cfg.min_account_balance}",
        )
    if risk <= 0 or risk > plan_cfg.max_risk_percent:
        raise HTTPException(
            status_code=422,
            detail=f"risk_percent must be in (0, {plan_cfg.max_risk_percent}]",
        )
    return balance, risk


async def compute_decision_response(
    *,
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    account_balance: float | None = None,
    risk_percent: float | None = None,
    decision_config: DecisionConfig | None = None,
    trade_plan_config: TradePlanConfig | None = None,
    as_of: datetime | None = None,
) -> DecisionResponse:
    d_cfg = decision_config or DEFAULT_DECISION_CONFIG
    p_cfg = trade_plan_config or DEFAULT_TRADE_PLAN_CONFIG
    balance, risk = _validate_sizing(account_balance, risk_percent, p_cfg)

    ctx = await build_analysis_context(
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        as_of=as_of,
    )
    trade_plan = analyze_trade_plan(
        exchange=exchange,
        symbol=symbol,
        market_type=market_type,
        confluence=ctx.confluence,
        mtf_snapshot=ctx.mtf_snapshot,
        bundles=ctx.bundles,
        candles_by_tf=ctx.candles_by_tf,
        account_balance=balance,
        risk_percent=risk,
        config=p_cfg,
        as_of=ctx.as_of,
    )
    result = analyze_decision(
        exchange=exchange,
        symbol=symbol,
        market_type=market_type,
        confluence=ctx.confluence,
        trade_plan=trade_plan,
        mtf_snapshot=ctx.mtf_snapshot,
        bundles=ctx.bundles,
        candles_by_tf=ctx.candles_by_tf,
        config=d_cfg,
        as_of=ctx.as_of,
    )

    return DecisionResponse(
        exchange=result.exchange,
        symbol=result.symbol,
        market_type=result.market_type,
        decision_id=result.decision_id,
        decision=result.decision,
        decision_reason=result.decision_reason,
        direction=result.direction,
        lifecycle=result.lifecycle,
        confluence_scores=result.confluence_scores,
        trade_plan_status=result.trade_plan_status,
        trade_plan_id=result.trade_plan_id,
        entry_confirmation=result.entry_confirmation,
        entry_zone_summary=result.entry_zone_summary,
        stop_loss_price=result.stop_loss_price,
        take_profit_prices=result.take_profit_prices,
        primary_rr=result.primary_rr,
        risk_amount=result.risk_amount,
        position_size=result.position_size,
        price_inside_entry_zone=result.price_inside_entry_zone,
        supporting_evidence=result.supporting_evidence,
        blocking_conditions=result.blocking_conditions,
        conflict_ids=result.conflict_ids,
        data_quality=result.data_quality,
        spot_restriction=result.spot_restriction,
        analysis_only_disclaimer=result.analysis_only_disclaimer,
        configuration_version=result.configuration_version,
        analysis_timestamp=result.analysis_timestamp,
        setup_detected_at=result.setup_detected_at,
        expires_at=result.expires_at,
        config=d_cfg.snapshot(),
        data_source=f"{exchange.value}:{market_type.value}",
        metadata=result.metadata,
    )
