"""Historical analysis pipeline — pure engines on replay prefixes (Phase 5.2.1)."""

from __future__ import annotations

import logging
from datetime import datetime

from app.analysis.confluence.config import DEFAULT_CONFLUENCE_CONFIG
from app.analysis.decision_engine import analyze_decision
from app.analysis.decision_engine.config import DEFAULT_DECISION_CONFIG
from app.analysis.indicators import calculate_indicators
from app.analysis.indicators.models import IndicatorBundle
from app.analysis.multi_timeframe.config import DEFAULT_MTF_CONFIG
from app.analysis.trade_plan import analyze_trade_plan
from app.analysis.trade_plan.config import DEFAULT_TRADE_PLAN_CONFIG
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.replay.analysis.config import (
    DEFAULT_HISTORICAL_ANALYSIS_CONFIG,
    STRATEGY_CONFIG_VERSION,
    HistoricalAnalysisConfig,
)
from app.replay.analysis.context_builder import (
    HistoricalPrefixContext,
    build_historical_prefixes,
)
from app.replay.analysis.models import HistoricalAnalysisSnapshot
from app.replay.analysis.snapshot import build_historical_snapshot
from app.replay.analysis.validation import LookAheadError
from app.replay.timeline import ensure_utc
from app.services.analysis_context import build_analysis_context_from_candles

logger = logging.getLogger(__name__)


def _analysis_versions() -> dict[str, str]:
    return {
        "historical_analysis": STRATEGY_CONFIG_VERSION,
        "mtf": DEFAULT_MTF_CONFIG.config_version,
        "confluence": DEFAULT_CONFLUENCE_CONFIG.config_version,
        "trade_plan": DEFAULT_TRADE_PLAN_CONFIG.config_version,
        "decision": DEFAULT_DECISION_CONFIG.config_version,
    }


def run_historical_analysis(
    *,
    session_id: str,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    series_by_tf: dict[Timeframe, list[Candle]],
    clock: datetime,
    event_index: int,
    account_balance: float | None = None,
    risk_percent: float | None = None,
    config: HistoricalAnalysisConfig | None = None,
) -> HistoricalAnalysisSnapshot:
    """
    Run Phases 3.1–4.4 on the closed-candle prefix available at ``clock``.

    Deterministic. Never fetches live market data. Never advances the replay clock.
    """
    cfg = config or DEFAULT_HISTORICAL_ANALYSIS_CONFIG
    clock = ensure_utc(clock)
    versions = _analysis_versions()

    try:
        prefix = build_historical_prefixes(
            session_id=session_id,
            exchange=exchange,
            symbol=symbol,
            market_type=market_type,
            series_by_tf=series_by_tf,
            clock=clock,
            config=cfg,
        )
    except LookAheadError as exc:
        logger.error("Look-ahead blocked: %s", exc)
        empty_prefix = HistoricalPrefixContext(
            session_id=session_id,
            replay_timestamp=clock,
            exchange=exchange,
            symbol=symbol.upper(),
            market_type=market_type,
            candles_by_tf={},
            closed_counts={},
            limitations=[str(exc)],
            is_ready=False,
        )
        return build_historical_snapshot(
            prefix=empty_prefix,
            event_index=event_index,
            ctx=None,
            decision=None,
            trade_plan=None,
            indicator_bundles={},
            analysis_versions=versions,
            analysis_error=str(exc),
            config_version=cfg.config_version,
        )

    indicator_bundles: dict[Timeframe, IndicatorBundle] = {}
    for tf in cfg.timeframes:
        candles = prefix.candles_by_tf.get(tf, [])
        try:
            indicator_bundles[tf] = calculate_indicators(
                candles,
                indicators=cfg.indicators,
                include_forming=False,
                include_series=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Historical indicators failed for %s: %s", tf.value, exc)

    ctx = None
    trade_plan = None
    decision = None
    analysis_error: str | None = None
    try:
        ctx = build_analysis_context_from_candles(
            prefix.candles_by_tf,
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
            as_of=clock,
        )
        plan_cfg = DEFAULT_TRADE_PLAN_CONFIG
        balance = (
            float(account_balance)
            if account_balance is not None
            else plan_cfg.default_account_balance
        )
        risk = (
            float(risk_percent)
            if risk_percent is not None
            else plan_cfg.default_risk_percent
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
            config=plan_cfg,
            as_of=clock,
        )
        decision = analyze_decision(
            exchange=exchange,
            symbol=symbol,
            market_type=market_type,
            confluence=ctx.confluence,
            trade_plan=trade_plan,
            mtf_snapshot=ctx.mtf_snapshot,
            bundles=ctx.bundles,
            candles_by_tf=ctx.candles_by_tf,
            config=DEFAULT_DECISION_CONFIG,
            as_of=clock,
        )
    except Exception as exc:  # noqa: BLE001
        analysis_error = str(exc)
        logger.exception("Historical analysis pipeline failed: %s", exc)

    return build_historical_snapshot(
        prefix=prefix,
        event_index=event_index,
        ctx=ctx,
        decision=decision,
        trade_plan=trade_plan,
        indicator_bundles=indicator_bundles,
        analysis_versions=versions,
        analysis_error=analysis_error,
        config_version=cfg.config_version,
    )
