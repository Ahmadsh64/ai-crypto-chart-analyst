"""Deterministic final trading decision engine (Phase 4.4)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.analysis.confluence.engine import TimeframeAnalysisBundle
from app.analysis.confluence.models import ConfluenceResult
from app.analysis.decision_engine.config import DEFAULT_DECISION_CONFIG, DecisionConfig
from app.analysis.decision_engine.decision_rules import (
    expires_at,
    is_setup_expired,
    is_setup_invalidated,
    resolve_decision,
)
from app.analysis.decision_engine.eligibility import evaluate_decision_eligibility
from app.analysis.decision_engine.entry_confirmation import evaluate_entry_confirmation
from app.analysis.decision_engine.models import (
    ConfluenceScoreSummary,
    DecisionDataQuality,
    DecisionResult,
)
from app.analysis.multi_timeframe.models import MultiTimeframeSnapshot
from app.analysis.trade_plan.models import TradePlanResult
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe


def analyze_decision(
    *,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    confluence: ConfluenceResult,
    trade_plan: TradePlanResult,
    mtf_snapshot: MultiTimeframeSnapshot,
    bundles: dict[Timeframe, TimeframeAnalysisBundle],
    candles_by_tf: dict[Timeframe, list[Candle]],
    config: DecisionConfig | None = None,
    as_of: datetime | None = None,
) -> DecisionResult:
    cfg = config or DEFAULT_DECISION_CONFIG
    now = as_of or datetime.now(timezone.utc)

    tf_map = {s.timeframe: s for s in mtf_snapshot.timeframes}
    setup_summary = tf_map.get(cfg.setup_timeframe)
    current_price = None
    if setup_summary and setup_summary.latest_price is not None:
        current_price = setup_summary.latest_price
    else:
        for tf in (Timeframe.M5, Timeframe.M15, Timeframe.H1):
            s = tf_map.get(tf)
            if s and s.latest_price is not None:
                current_price = s.latest_price
                break

    eligibility = evaluate_decision_eligibility(
        confluence=confluence,
        trade_plan=trade_plan,
        mtf_snapshot=mtf_snapshot,
        config=cfg,
    )

    direction = eligibility.direction or trade_plan.direction
    confirm_bundle = bundles.get(cfg.confirmation_timeframe)
    confirm_candles = candles_by_tf.get(cfg.confirmation_timeframe, [])

    if direction:
        confirmation = evaluate_entry_confirmation(
            direction=direction,
            confirm_bundle=confirm_bundle,
            confirm_candles=confirm_candles,
            as_of=now,
            config=cfg,
        )
    else:
        from app.analysis.decision_engine.models import EntryConfirmationResult

        confirmation = EntryConfirmationResult(
            status="unavailable",
            explanation="No directional setup to confirm.",
            blocking_reasons=["No direction."],
        )

    price_inside = False
    if trade_plan.entry is not None and current_price is not None:
        price_inside = (
            trade_plan.entry.entry_low
            <= current_price
            <= trade_plan.entry.entry_high
        )

    setup_candles = candles_by_tf.get(cfg.setup_timeframe, [])
    expired = is_setup_expired(
        trade_plan=trade_plan,
        setup_candles=setup_candles,
        as_of=now,
        config=cfg,
    )
    sl_breached = False
    if (
        trade_plan.plan_status == "eligible"
        and trade_plan.stop_loss is not None
        and trade_plan.direction is not None
        and current_price is not None
    ):
        sl = trade_plan.stop_loss.stop_loss_price
        if trade_plan.direction == "bullish" and current_price <= sl:
            sl_breached = True
        if trade_plan.direction == "bearish" and current_price >= sl:
            sl_breached = True

    both = (
        confluence.bullish_score >= cfg.min_directional_score
        and confluence.bearish_score >= cfg.min_directional_score
        and abs(confluence.bullish_score - confluence.bearish_score) < cfg.min_score_margin
    )

    decision, lifecycle, reason, extra_blockers = resolve_decision(
        eligibility=eligibility,
        confirmation=confirmation,
        trade_plan=trade_plan,
        market_type=market_type,
        current_price=current_price,
        price_inside_zone=price_inside,
        setup_expired=expired,
        setup_invalidated=sl_breached or is_setup_invalidated(
            trade_plan=trade_plan,
            current_price=None,  # plan status only; SL handled via sl_breached
        ),
        both_directions_valid=both,
        config=cfg,
    )

    blocking = list(eligibility.blocking_reasons) + list(extra_blockers)
    if decision in {"WAIT"} and confirmation.blocking_reasons:
        blocking = list(dict.fromkeys(blocking + confirmation.blocking_reasons))

    supporting = list(trade_plan.supporting_evidence_ids[:12])
    supporting.extend(confirmation.evidence_ids)

    conflict_ids = [
        f"{c.conflict_type}:{c.severity.value}:{i}"
        for i, c in enumerate(confluence.conflicts)
    ]

    spot_restriction = None
    if market_type == MarketType.SPOT and direction == "bearish":
        spot_restriction = (
            "Spot market: SHORT is not directly executable as a standard Spot trade."
        )

    entry_summary = None
    if trade_plan.entry is not None:
        e = trade_plan.entry
        entry_summary = {
            "entry_low": e.entry_low,
            "entry_high": e.entry_high,
            "entry_reference_price": e.entry_reference_price,
            "entry_type": e.entry_type,
            "entry_source": e.entry_source,
            "source_event_key": e.source_event_key,
            "price_inside_zone": price_inside,
        }

    dq = DecisionDataQuality(
        overall=mtf_snapshot.overall_status,
        is_analysis_complete=mtf_snapshot.overall_status == "ready",
        timeframes_used=[s.timeframe.value for s in mtf_snapshot.timeframes if s.is_ready],
        timeframes_unavailable=[t.value for t in mtf_snapshot.unavailable_timeframes],
        timeframes_stale=[
            s.timeframe.value
            for s in mtf_snapshot.timeframes
            if s.is_stale or s.data_quality == "stale"
        ],
        limitations=list(trade_plan.data_quality.limitations),
        current_price=current_price,
    )

    # Lifecycle nuance: valid setup first seen without confirm → awaiting / setup_detected
    if decision == "WAIT" and eligibility.is_setup_valid and lifecycle == "awaiting_confirmation":
        lifecycle = "awaiting_confirmation"
    elif decision == "NO TRADE" and not eligibility.is_setup_valid and not expired:
        if not any(
            "conflict" in b.lower() or "stale" in b.lower() or "missing" in b.lower()
            for b in eligibility.blocking_reasons
        ):
            lifecycle = "setup_detected" if confluence.bullish_score + confluence.bearish_score > 0 else "invalidated"

    decision_id = _id(exchange, market_type, symbol, now, cfg.config_version, decision)

    return DecisionResult(
        decision_id=decision_id,
        exchange=exchange,
        symbol=symbol.upper(),
        market_type=market_type,
        decision=decision,
        decision_reason=reason,
        direction=direction,
        lifecycle=lifecycle,
        confluence_scores=ConfluenceScoreSummary(
            bullish_score=confluence.bullish_score,
            bearish_score=confluence.bearish_score,
            preliminary_assessment=confluence.preliminary_assessment.value,
            assessment_strength=confluence.assessment_strength,
        ),
        trade_plan_status=trade_plan.plan_status,
        trade_plan_id=trade_plan.plan_id,
        entry_confirmation=confirmation,
        entry_zone_summary=entry_summary,
        stop_loss_price=(
            trade_plan.stop_loss.stop_loss_price if trade_plan.stop_loss else None
        ),
        take_profit_prices=[t.price for t in trade_plan.take_profit_targets],
        primary_rr=trade_plan.risk.primary_rr if trade_plan.risk else None,
        risk_amount=(
            trade_plan.position_sizing.risk_amount if trade_plan.position_sizing else None
        ),
        position_size=(
            trade_plan.position_sizing.position_size if trade_plan.position_sizing else None
        ),
        price_inside_entry_zone=price_inside if trade_plan.entry else None,
        supporting_evidence=supporting,
        blocking_conditions=_unique(blocking),
        conflict_ids=conflict_ids,
        data_quality=dq,
        spot_restriction=spot_restriction,
        configuration_version=cfg.config_version,
        analysis_timestamp=now,
        setup_detected_at=trade_plan.analysis_timestamp if eligibility.is_setup_valid else None,
        expires_at=expires_at(now, cfg) if eligibility.is_setup_valid else None,
        metadata={
            "no_order_execution": True,
            "leverage_recommended": False,
            "analytical_entry_only": True,
        },
    )


def _id(
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    when: datetime,
    version: str,
    decision: str,
) -> str:
    raw = f"{exchange.value}|{market_type.value}|{symbol}|{when.isoformat()}|{version}|{decision}"
    return "dec_" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out
