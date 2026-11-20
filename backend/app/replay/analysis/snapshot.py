"""Compact historical analysis snapshot builders (Phase 5.2.1)."""

from __future__ import annotations

from typing import Any

from app.analysis.confluence.models import ConfluenceResult
from app.analysis.decision_engine.models import DecisionResult
from app.analysis.indicators.models import IndicatorBundle
from app.analysis.trade_plan.models import TradePlanResult
from app.exchanges.types import Timeframe
from app.replay.analysis.config import STRATEGY_CONFIG_VERSION
from app.replay.analysis.context_builder import HistoricalPrefixContext
from app.replay.analysis.models import (
    HistoricalAnalysisSnapshot,
    IndicatorLatestSummary,
    LiquiditySummary,
    ObFvgSummary,
    StructureSummary,
)
from app.services.analysis_context import AnalysisContext


def build_historical_snapshot(
    *,
    prefix: HistoricalPrefixContext,
    event_index: int,
    ctx: AnalysisContext | None,
    decision: DecisionResult | None,
    trade_plan: TradePlanResult | None,
    indicator_bundles: dict[Timeframe, IndicatorBundle],
    analysis_versions: dict[str, str],
    analysis_error: str | None = None,
    config_version: str = STRATEGY_CONFIG_VERSION,
) -> HistoricalAnalysisSnapshot:
    indicators: dict[str, IndicatorLatestSummary] = {}
    for tf, bundle in indicator_bundles.items():
        values: dict[str, float | None] = {}
        statuses: dict[str, str] = {}
        warming = False
        for key, latest in bundle.latest.items():
            statuses[key] = str(latest.status)
            if str(latest.status) in {"warming_up", "insufficient_data"}:
                warming = True
            if latest.value is not None:
                values[key] = latest.value
            for field, val in (latest.fields or {}).items():
                values[f"{key}.{field}"] = val
        indicators[tf.value] = IndicatorLatestSummary(
            timeframe=tf,
            values=values,
            statuses=statuses,
            closed_candles_used=bundle.closed_candles_used,
            warming_up=warming,
        )

    structure: dict[str, StructureSummary] = {}
    liquidity: dict[str, LiquiditySummary] = {}
    ob_fvg: dict[str, ObFvgSummary] = {}
    if ctx is not None:
        for tf, b in ctx.bundles.items():
            if b.structure is not None:
                s = b.structure
                latest = None
                if s.mss_events:
                    latest = f"mss:{s.mss_events[-1].direction}"
                elif s.choch_events:
                    latest = f"choch:{s.choch_events[-1].direction}"
                elif s.bos_events:
                    latest = f"bos:{s.bos_events[-1].direction}"
                bias = None
                if s.snapshot is not None:
                    bias = str(s.snapshot.bias)
                structure[tf.value] = StructureSummary(
                    timeframe=tf,
                    bias=bias,
                    swing_count=len(s.swings),
                    bos_count=len(s.bos_events),
                    choch_count=len(s.choch_events),
                    mss_count=len(s.mss_events),
                    latest_event=latest,
                )
            if b.liquidity is not None:
                liq = b.liquidity
                latest_sweep = None
                if liq.sweeps:
                    sw = liq.sweeps[-1]
                    hint = sw.reaction_hint.value if sw.reaction_hint else None
                    latest_sweep = f"{sw.liquidity_type.value}:{hint}"
                liquidity[tf.value] = LiquiditySummary(
                    timeframe=tf,
                    eqh_count=len(liq.eqh_clusters),
                    eql_count=len(liq.eql_clusters),
                    bsl_count=len(liq.bsl_levels),
                    ssl_count=len(liq.ssl_levels),
                    sweep_count=len(liq.sweeps),
                    latest_sweep=latest_sweep,
                )
            if b.ob_fvg is not None:
                ob = b.ob_fvg
                zones = (
                    list(ob.bullish_order_blocks)
                    + list(ob.bearish_order_blocks)
                    + list(ob.bullish_fvgs)
                    + list(ob.bearish_fvgs)
                )
                active = 0
                for z in zones:
                    st = str(getattr(z, "status", "")).lower()
                    if st in {
                        "fresh",
                        "active",
                        "partial",
                        "unmitigated",
                        "forming",
                        "untouched",
                    }:
                        active += 1
                ob_fvg[tf.value] = ObFvgSummary(
                    timeframe=tf,
                    bullish_ob_count=len(ob.bullish_order_blocks),
                    bearish_ob_count=len(ob.bearish_order_blocks),
                    bullish_fvg_count=len(ob.bullish_fvgs),
                    bearish_fvg_count=len(ob.bearish_fvgs),
                    active_zone_count=active,
                )

    confluence: ConfluenceResult | None = ctx.confluence if ctx else None
    limitations = list(prefix.limitations)
    if decision is not None:
        limitations.extend(decision.data_quality.limitations)
    if analysis_error:
        limitations.append(analysis_error)

    data_quality = "insufficient"
    data_ready = prefix.is_ready
    if decision is not None:
        data_quality = decision.data_quality.overall
        data_ready = decision.data_quality.is_analysis_complete
    elif confluence is not None:
        data_quality = confluence.data_quality.overall
        data_ready = confluence.data_quality.is_analysis_complete

    entry_zone = None
    if decision and decision.entry_zone_summary:
        entry_zone = decision.entry_zone_summary
    elif trade_plan and trade_plan.entry is not None:
        entry_zone = trade_plan.entry.model_dump(mode="json")

    stop_loss = None
    if decision and decision.stop_loss_price is not None:
        stop_loss = decision.stop_loss_price
    elif trade_plan and trade_plan.stop_loss is not None:
        stop_loss = trade_plan.stop_loss.stop_loss_price

    take_profits: list[float] = []
    if decision and decision.take_profit_prices:
        take_profits = list(decision.take_profit_prices)
    elif trade_plan:
        take_profits = [t.price for t in trade_plan.take_profit_targets]

    risk_reward = None
    if decision and decision.primary_rr is not None:
        risk_reward = decision.primary_rr
    elif trade_plan and trade_plan.risk is not None:
        risk_reward = trade_plan.risk.primary_rr

    evidence_summary: list[str] = []
    if decision and decision.supporting_evidence:
        evidence_summary = list(decision.supporting_evidence[:12])
    elif confluence:
        evidence_summary = [e.explanation for e in confluence.evidence[:12]]

    conflicts: list[str] = []
    if confluence:
        conflicts = [c.description for c in confluence.conflicts]

    return HistoricalAnalysisSnapshot(
        session_id=prefix.session_id,
        replay_timestamp=prefix.replay_timestamp,
        event_index=event_index,
        exchange=prefix.exchange,
        symbol=prefix.symbol,
        market_type=prefix.market_type,
        decision=str(decision.decision) if decision else "NO TRADE",
        decision_reason=(
            decision.decision_reason
            if decision
            else (analysis_error or "Analysis unavailable.")
        ),
        lifecycle_status=str(decision.lifecycle) if decision else "none",
        direction=decision.direction if decision else None,
        bullish_score=float(confluence.bullish_score) if confluence else 0.0,
        bearish_score=float(confluence.bearish_score) if confluence else 0.0,
        confluence_strength=(confluence.assessment_strength if confluence else None),
        preliminary_assessment=(
            confluence.preliminary_assessment.value if confluence else None
        ),
        conflicts=conflicts,
        evidence_summary=evidence_summary,
        entry_zone=entry_zone,
        stop_loss=stop_loss,
        take_profit_levels=take_profits,
        risk_reward=risk_reward,
        trade_plan_status=(
            decision.trade_plan_status
            if decision
            else (str(trade_plan.plan_status) if trade_plan else None)
        ),
        position_size=(
            decision.position_size
            if decision
            else (
                trade_plan.position_sizing.position_size
                if trade_plan and trade_plan.position_sizing
                else None
            )
        ),
        expires_at=decision.expires_at if decision else None,
        decision_id=decision.decision_id if decision else None,
        trade_plan_id=(
            decision.trade_plan_id
            if decision
            else (trade_plan.plan_id if trade_plan else None)
        ),
        indicators=indicators,
        structure=structure,
        liquidity=liquidity,
        ob_fvg=ob_fvg,
        closed_candle_counts={tf.value: n for tf, n in prefix.closed_counts.items()},
        data_quality=data_quality,
        data_ready=data_ready,
        limitations=list(dict.fromkeys(limitations)),
        analysis_versions=analysis_versions,
        analysis_error=analysis_error,
        config_version=config_version,
        analysis_timestamp=prefix.replay_timestamp,
    )


def snapshot_ws_payload(snap: HistoricalAnalysisSnapshot) -> dict[str, Any]:
    """Lean payload for replay_analysis_update WebSocket events."""
    return {
        "session_id": snap.session_id,
        "replay_timestamp": snap.replay_timestamp.isoformat(),
        "exchange": snap.exchange.value,
        "symbol": snap.symbol,
        "market_type": snap.market_type.value,
        "decision": snap.decision,
        "lifecycle_status": snap.lifecycle_status,
        "bullish_score": snap.bullish_score,
        "bearish_score": snap.bearish_score,
        "confluence_strength": snap.confluence_strength,
        "entry_zone": snap.entry_zone,
        "stop_loss": snap.stop_loss,
        "take_profit_levels": snap.take_profit_levels,
        "risk_reward": snap.risk_reward,
        "data_quality": snap.data_quality,
        "analysis_versions": snap.analysis_versions,
        "decision_reason": snap.decision_reason,
        "evidence_summary": snap.evidence_summary,
        "conflicts": snap.conflicts,
        "hypothetical_plan_disclaimer": snap.hypothetical_plan_disclaimer,
    }
