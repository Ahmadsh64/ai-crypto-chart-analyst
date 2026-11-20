"""REST service for deterministic trade plans (Phase 4.3)."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException

from app.analysis.trade_plan import analyze_trade_plan
from app.analysis.trade_plan.config import DEFAULT_TRADE_PLAN_CONFIG, TradePlanConfig
from app.api.schemas.trade_plan import TradePlanResponse
from app.exchanges.types import ExchangeId, MarketType
from app.services.analysis_context import build_analysis_context


def _validate_sizing_inputs(
    account_balance: float | None,
    risk_percent: float | None,
    config: TradePlanConfig,
) -> tuple[float, float]:
    balance = (
        float(account_balance)
        if account_balance is not None
        else config.default_account_balance
    )
    risk = float(risk_percent) if risk_percent is not None else config.default_risk_percent
    if balance < config.min_account_balance:
        raise HTTPException(
            status_code=422,
            detail=f"account_balance must be >= {config.min_account_balance}",
        )
    if risk <= 0 or risk > config.max_risk_percent:
        raise HTTPException(
            status_code=422,
            detail=f"risk_percent must be in (0, {config.max_risk_percent}]",
        )
    return balance, risk


async def compute_trade_plan_response(
    *,
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    account_balance: float | None = None,
    risk_percent: float | None = None,
    config: TradePlanConfig | None = None,
    as_of: datetime | None = None,
) -> TradePlanResponse:
    cfg = config or DEFAULT_TRADE_PLAN_CONFIG
    balance, risk = _validate_sizing_inputs(account_balance, risk_percent, cfg)

    ctx = await build_analysis_context(
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        as_of=as_of,
    )
    result = analyze_trade_plan(
        exchange=exchange,
        symbol=symbol,
        market_type=market_type,
        confluence=ctx.confluence,
        mtf_snapshot=ctx.mtf_snapshot,
        bundles=ctx.bundles,
        candles_by_tf=ctx.candles_by_tf,
        account_balance=balance,
        risk_percent=risk,
        config=cfg,
        as_of=ctx.as_of,
    )

    return TradePlanResponse(
        exchange=result.exchange,
        symbol=result.symbol,
        market_type=result.market_type,
        plan_id=result.plan_id,
        direction=result.direction,
        plan_status=result.plan_status,
        entry=result.entry,
        stop_loss=result.stop_loss,
        take_profit_targets=result.take_profit_targets,
        risk=result.risk,
        position_sizing=result.position_sizing,
        validation=result.validation,
        eligibility=result.eligibility,
        supporting_evidence_ids=result.supporting_evidence_ids,
        conflict_ids=result.conflict_ids,
        invalidation_conditions=result.invalidation_conditions,
        explanations=result.explanations,
        configuration_version=result.configuration_version,
        analysis_timestamp=result.analysis_timestamp,
        data_quality=result.data_quality,
        confluence_assessment=result.confluence_assessment,
        confluence_assessment_strength=result.confluence_assessment_strength,
        bullish_score=result.bullish_score,
        bearish_score=result.bearish_score,
        spot_short_warning=result.spot_short_warning,
        analysis_only_disclaimer=result.analysis_only_disclaimer,
        config=cfg.snapshot(),
        data_source=f"{exchange.value}:{market_type.value}",
        metadata=result.metadata,
    )
