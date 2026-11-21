"""Analyze one candidate × execution timeframe with existing engines only (Phase 5.5)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.analysis.decision_engine import analyze_decision
from app.analysis.multi_timeframe.config import DEFAULT_MTF_CONFIG
from app.analysis.trade_plan import analyze_trade_plan
from app.exchanges.manager import get_exchange_manager
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.scanner.config import ScannerConfig
from app.scanner.eligibility import (
    classify_opportunity_status,
    entry_distance_pct,
    is_actionable,
)
from app.scanner.execution_timeframes import (
    decision_config_for_execution,
    trade_plan_config_for_execution,
)
from app.scanner.identity import (
    compute_opportunity_id,
    compute_slot_key,
    fingerprint_from_opportunity,
)
from app.scanner.models import (
    MarketOpportunity,
    OpportunityDirection,
    OpportunityLevel,
    OpportunityStatus,
)
from app.scanner.ohlcv_cache import OhlcvTtlCache
from app.scanner.universe import ScanCandidate
from app.services.analysis_context import build_analysis_context_from_candles


def _tp_levels(prices: list[float], plan_targets: list) -> list[OpportunityLevel]:
    by_index: dict[int, float] = {}
    for t in plan_targets:
        by_index[int(t.index)] = float(t.price)
    for i, p in enumerate(prices, start=1):
        by_index.setdefault(i, float(p))
    out: list[OpportunityLevel] = []
    for i in range(1, 4):
        price = by_index.get(i)
        out.append(
            OpportunityLevel(
                label=f"TP{i}",
                price=price,
                available=price is not None,
            )
        )
    return out


def _unavailable_tps() -> list[OpportunityLevel]:
    return [
        OpportunityLevel(label="TP1", available=False),
        OpportunityLevel(label="TP2", available=False),
        OpportunityLevel(label="TP3", available=False),
    ]


async def load_mtf_candles(
    *,
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    cache: OhlcvTtlCache,
) -> dict[Timeframe, list[Candle]]:
    """Fetch full MTF ladder (4H→1H→15M→5M). Shared across execution-TF analyses."""
    manager = get_exchange_manager()
    mtf_cfg = DEFAULT_MTF_CONFIG
    out: dict[Timeframe, list[Candle]] = {}
    for tf in mtf_cfg.timeframes:
        cached = cache.get(exchange, market_type, symbol, tf)
        if cached is not None:
            out[tf] = cached
            continue
        limit = mtf_cfg.history_for(tf).fetch_limit
        candles = await manager.fetch_ohlcv(
            exchange, symbol, tf, market_type, limit=limit
        )
        cache.set(exchange, market_type, symbol, tf, candles)
        out[tf] = candles
    return out


async def analyze_candidate(
    candidate: ScanCandidate,
    *,
    config: ScannerConfig,
    cache: OhlcvTtlCache,
    execution_timeframe: Timeframe,
) -> MarketOpportunity:
    """
    Run deterministic Trade Plan + Decision for one execution timeframe.

    Always loads the complete MTF ladder. Uses config overlays for setup/confirm
    roles only — never changes scores, RR, or eligibility thresholds.
    """
    slot_key = compute_slot_key(
        candidate.exchange,
        candidate.market_type,
        candidate.symbol,
        execution_timeframe,
    )
    # Provisional id (generation 0) until persistence allocates setup_generation.
    oid = compute_opportunity_id(slot_key, 0, "provisional")
    now = datetime.now(timezone.utc)
    decision_cfg = decision_config_for_execution(execution_timeframe)
    plan_cfg = trade_plan_config_for_execution(execution_timeframe)

    try:
        candles_by_tf = await load_mtf_candles(
            exchange=candidate.exchange,
            market_type=candidate.market_type,
            symbol=candidate.symbol,
            cache=cache,
        )
    except Exception as exc:  # noqa: BLE001
        return MarketOpportunity(
            opportunity_id=oid,
            exchange=candidate.exchange,
            market_type=candidate.market_type,
            symbol=candidate.symbol,
            base=candidate.base,
            timeframe=execution_timeframe,
            status=OpportunityStatus.DATA_UNAVAILABLE,
            decision_reason=f"OHLCV unavailable: {exc}",
            quote_volume_24h=candidate.quote_volume_24h,
            analysis_timestamp=now,
            actionable=False,
            take_profits=_unavailable_tps(),
            metadata={"execution_timeframe": execution_timeframe.value},
        )

    closed_any = any(any(c.is_closed for c in series) for series in candles_by_tf.values())
    if not closed_any:
        return MarketOpportunity(
            opportunity_id=oid,
            exchange=candidate.exchange,
            market_type=candidate.market_type,
            symbol=candidate.symbol,
            base=candidate.base,
            timeframe=execution_timeframe,
            status=OpportunityStatus.DATA_UNAVAILABLE,
            decision_reason="Insufficient closed candles",
            quote_volume_24h=candidate.quote_volume_24h,
            analysis_timestamp=now,
            actionable=False,
            take_profits=_unavailable_tps(),
            metadata={"execution_timeframe": execution_timeframe.value},
        )

    ctx = build_analysis_context_from_candles(
        candles_by_tf,
        exchange=candidate.exchange,
        market_type=candidate.market_type,
        symbol=candidate.symbol,
        as_of=now,
    )

    trade_plan = analyze_trade_plan(
        exchange=candidate.exchange,
        symbol=candidate.symbol,
        market_type=candidate.market_type,
        confluence=ctx.confluence,
        mtf_snapshot=ctx.mtf_snapshot,
        bundles=ctx.bundles,
        candles_by_tf=ctx.candles_by_tf,
        account_balance=plan_cfg.default_account_balance,
        risk_percent=plan_cfg.default_risk_percent,
        config=plan_cfg,
        as_of=ctx.as_of,
    )
    decision = analyze_decision(
        exchange=candidate.exchange,
        symbol=candidate.symbol,
        market_type=candidate.market_type,
        confluence=ctx.confluence,
        trade_plan=trade_plan,
        mtf_snapshot=ctx.mtf_snapshot,
        bundles=ctx.bundles,
        candles_by_tf=ctx.candles_by_tf,
        config=decision_cfg,
        as_of=ctx.as_of,
    )

    current_price = decision.data_quality.current_price
    # Prefer execution TF last close, then ladder fallbacks.
    if current_price is None:
        for tf in (execution_timeframe, Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4):
            series = candles_by_tf.get(tf) or []
            if series:
                current_price = series[-1].close
                break

    data_ok = bool(decision.data_quality.is_analysis_complete)
    status = classify_opportunity_status(
        decision=decision,
        trade_plan=trade_plan,
        current_price=current_price,
        config=config,
        data_ok=data_ok or decision.decision in ("LONG", "SHORT", "WAIT", "NO TRADE"),
    )

    # Planned levels: expose whenever Trade Plan is eligible with real levels.
    # Final Decision may still be WAIT — do not invent levels; do not force LONG/SHORT.
    plan_eligible = (
        trade_plan.plan_status == "eligible"
        and trade_plan.entry is not None
        and trade_plan.stop_loss is not None
        and bool(trade_plan.take_profit_targets)
    )
    entry_low = entry_high = entry_ref = None
    stop = None
    if plan_eligible and trade_plan.entry is not None:
        entry_low = trade_plan.entry.entry_low
        entry_high = trade_plan.entry.entry_high
        entry_ref = trade_plan.entry.entry_reference_price
    if plan_eligible and trade_plan.stop_loss is not None:
        stop = trade_plan.stop_loss.stop_loss_price

    show_levels = plan_eligible
    tps = (
        _tp_levels(decision.take_profit_prices, trade_plan.take_profit_targets)
        if show_levels
        else _unavailable_tps()
    )
    primary_rr = None
    if show_levels:
        if decision.primary_rr is not None:
            primary_rr = decision.primary_rr
        elif trade_plan.risk is not None:
            primary_rr = trade_plan.risk.primary_rr

    bull = decision.confluence_scores.bullish_score
    bear = decision.confluence_scores.bearish_score
    confluence_score = max(bull, bear)

    # Planned direction from Decision LONG/SHORT, else eligible Trade Plan side.
    direction: OpportunityDirection | None = None
    if decision.decision == "LONG":
        direction = OpportunityDirection.LONG
    elif decision.decision == "SHORT":
        direction = OpportunityDirection.SHORT
    elif plan_eligible and trade_plan.direction == "bullish":
        direction = OpportunityDirection.LONG
    elif plan_eligible and trade_plan.direction == "bearish":
        direction = OpportunityDirection.SHORT

    # Market executability (Spot SHORT never executable) — independent of READY.
    market_executable = True
    executability_note = ""
    if direction == OpportunityDirection.SHORT and candidate.market_type == MarketType.SPOT:
        market_executable = False
        executability_note = (
            "Analytical bearish plan — a standard Spot market cannot execute SHORT. "
            "Not an actionable Spot short opportunity."
        )
    elif status == OpportunityStatus.WAITING and plan_eligible:
        executability_note = (
            "Pending entry confirmation — planned levels are analytical only."
        )

    dist = entry_distance_pct(current_price, entry_low, entry_high, entry_ref)
    overlay_meta = {
        "execution_timeframe": execution_timeframe.value,
        "setup_timeframe": decision_cfg.setup_timeframe.value,
        "confirmation_timeframe": decision_cfg.confirmation_timeframe.value,
        "plan_status": trade_plan.plan_status,
        "entry_confirmation": decision.entry_confirmation.status,
        "mtf_ladder": [tf.value for tf in DEFAULT_MTF_CONFIG.timeframes],
        "slot_key": slot_key,
        "planned_levels_from_eligible_plan": show_levels,
        "final_decision_unchanged": decision.decision,
    }

    opportunity = MarketOpportunity(
        opportunity_id=oid,
        exchange=candidate.exchange,
        market_type=candidate.market_type,
        symbol=candidate.symbol,
        base=candidate.base,
        timeframe=execution_timeframe,
        status=status,
        decision=decision.decision,
        decision_reason=decision.decision_reason,
        direction=direction,
        market_executable=market_executable,
        executability_note=executability_note,
        current_price=current_price,
        price_updated_at=now,
        price_source=f"{candidate.exchange.value}:{candidate.market_type.value}",
        entry_reference=entry_ref if show_levels else None,
        entry_low=entry_low if show_levels else None,
        entry_high=entry_high if show_levels else None,
        stop_loss=stop if show_levels else None,
        take_profits=tps,
        primary_rr=primary_rr if show_levels else None,
        confluence_bullish=bull,
        confluence_bearish=bear,
        confluence_score=confluence_score,
        supporting_evidence=list(decision.supporting_evidence)[:8],
        blocking_conditions=list(decision.blocking_conditions)[:8],
        entry_distance_pct=dist,
        quote_volume_24h=candidate.quote_volume_24h,
        analysis_timestamp=decision.analysis_timestamp,
        decision_id=decision.decision_id,
        trade_plan_id=decision.trade_plan_id,
        lifecycle=decision.lifecycle,
        actionable=is_actionable(status),
        metadata=overlay_meta,
    )
    fp = fingerprint_from_opportunity(opportunity)
    opportunity.opportunity_id = compute_opportunity_id(slot_key, 0, fp)
    opportunity.metadata = {**opportunity.metadata, "setup_fingerprint": fp}
    return opportunity
