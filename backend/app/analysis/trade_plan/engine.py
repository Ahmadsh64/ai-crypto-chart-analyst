"""Deterministic trade-plan engine (Phase 4.3)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import numpy as np

from app.analysis.confluence.engine import TimeframeAnalysisBundle
from app.analysis.confluence.models import ConfluenceResult
from app.analysis.indicators.volatility import atr as atr_wilder
from app.analysis.multi_timeframe.models import MultiTimeframeSnapshot
from app.analysis.trade_plan.config import DEFAULT_TRADE_PLAN_CONFIG, TradePlanConfig
from app.analysis.trade_plan.eligibility import evaluate_eligibility
from app.analysis.trade_plan.entry import select_entry
from app.analysis.trade_plan.models import TradePlanDataQuality, TradePlanResult
from app.analysis.trade_plan.risk import calculate_position_sizing, calculate_risk_metrics
from app.analysis.trade_plan.stop_loss import calculate_stop_loss
from app.analysis.trade_plan.take_profit import calculate_take_profits
from app.analysis.trade_plan.validation import validate_plan
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe


def latest_atr(candles: list[Candle], period: int = 14) -> float | None:
    closed = [c for c in candles if c.is_closed]
    if len(closed) < period:
        return None
    high = np.asarray([c.high for c in closed], dtype=float)
    low = np.asarray([c.low for c in closed], dtype=float)
    close = np.asarray([c.close for c in closed], dtype=float)
    series = atr_wilder(high, low, close, period=period)
    val = float(series[-1])
    if val != val:  # NaN
        return None
    return val


def analyze_trade_plan(
    *,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    confluence: ConfluenceResult,
    mtf_snapshot: MultiTimeframeSnapshot,
    bundles: dict[Timeframe, TimeframeAnalysisBundle],
    candles_by_tf: dict[Timeframe, list[Candle]],
    account_balance: float | None = None,
    risk_percent: float | None = None,
    config: TradePlanConfig | None = None,
    as_of: datetime | None = None,
) -> TradePlanResult:
    cfg = config or DEFAULT_TRADE_PLAN_CONFIG
    now = as_of or datetime.now(timezone.utc)
    balance = (
        float(account_balance)
        if account_balance is not None
        else cfg.default_account_balance
    )
    risk_pct = float(risk_percent) if risk_percent is not None else cfg.default_risk_percent

    setup_tf = cfg.setup_timeframe
    tf_map = {s.timeframe: s for s in mtf_snapshot.timeframes}
    setup_summary = tf_map.get(setup_tf)
    current_price = None
    if setup_summary is not None and setup_summary.latest_price is not None:
        current_price = setup_summary.latest_price
    else:
        for tf in (Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4):
            s = tf_map.get(tf)
            if s and s.latest_price is not None:
                current_price = s.latest_price
                break

    atr_value = latest_atr(
        candles_by_tf.get(setup_tf, []),
        period=cfg.atr_period,
    )

    dq = _data_quality(mtf_snapshot, current_price=current_price, atr_available=atr_value is not None)

    eligibility = evaluate_eligibility(
        confluence,
        mtf_snapshot,
        current_price=current_price,
        config=cfg,
    )

    supporting = [
        e.evidence_id
        for e in confluence.evidence
        if not e.excluded
        and e.is_confirmed
        and eligibility.direction
        and e.direction.value == eligibility.direction
    ]
    conflict_ids = [
        f"{c.conflict_type}:{c.severity.value}:{idx}"
        for idx, c in enumerate(confluence.conflicts)
    ]

    plan_id = _plan_id(exchange, market_type, symbol, now, cfg.config_version)

    spot_warning = None
    if market_type == MarketType.SPOT and eligibility.direction == "bearish":
        spot_warning = (
            "Hypothetical downside scenario only — a short position cannot be executed "
            "as a standard Spot trade."
        )

    base_kwargs = dict(
        plan_id=plan_id,
        symbol=symbol.upper(),
        exchange=exchange,
        market_type=market_type,
        direction=eligibility.direction,
        supporting_evidence_ids=supporting,
        conflict_ids=conflict_ids,
        configuration_version=cfg.config_version,
        analysis_timestamp=now,
        data_quality=dq,
        confluence_assessment=confluence.preliminary_assessment.value,
        confluence_assessment_strength=confluence.assessment_strength,
        bullish_score=confluence.bullish_score,
        bearish_score=confluence.bearish_score,
        spot_short_warning=spot_warning,
        eligibility=eligibility,
        metadata={
            "no_order_execution": True,
            "hypothetical_sizing": True,
            "leverage_recommended": False,
        },
    )

    if not eligibility.is_eligible:
        validation = validate_plan(
            eligibility=eligibility,
            direction=eligibility.direction,
            entry=None,
            stop=None,
            targets=[],
            risk=None,
            sizing=None,
            market_type=market_type,
            config=cfg,
        )
        return TradePlanResult(
            **base_kwargs,  # type: ignore[arg-type]
            plan_status="blocked",
            validation=validation,
            explanations=list(eligibility.blocking_reasons),
            invalidation_conditions=[],
        )

    assert eligibility.direction is not None
    assert current_price is not None
    direction = eligibility.direction

    setup_bundle = bundles.get(setup_tf) or TimeframeAnalysisBundle()
    confirm_bundle = bundles.get(cfg.confirmation_timeframe) or TimeframeAnalysisBundle()

    entry, entry_blockers = select_entry(
        direction=direction,
        current_price=current_price,
        atr_value=atr_value,
        setup_ob_fvg=setup_bundle.ob_fvg,
        setup_structure=setup_bundle.structure,
        setup_timeframe=setup_tf.value,
        config=cfg,
    )
    if entry is None:
        validation = validate_plan(
            eligibility=eligibility,
            direction=direction,
            entry=None,
            stop=None,
            targets=[],
            risk=None,
            sizing=None,
            market_type=market_type,
            config=cfg,
        )
        validation.blocking_reasons = _unique(validation.blocking_reasons + entry_blockers)
        validation.is_valid = False
        return TradePlanResult(
            **base_kwargs,  # type: ignore[arg-type]
            plan_status="blocked",
            validation=validation,
            explanations=entry_blockers,
            invalidation_conditions=[],
        )

    stop, sl_notes = calculate_stop_loss(
        direction=direction,
        entry=entry,
        atr_value=atr_value,
        setup_structure=setup_bundle.structure,
        config=cfg,
    )
    if stop is None:
        validation = validate_plan(
            eligibility=eligibility,
            direction=direction,
            entry=entry,
            stop=None,
            targets=[],
            risk=None,
            sizing=None,
            market_type=market_type,
            config=cfg,
        )
        validation.blocking_reasons = _unique(validation.blocking_reasons + sl_notes)
        validation.is_valid = False
        return TradePlanResult(
            **base_kwargs,  # type: ignore[arg-type]
            plan_status="blocked",
            entry=entry,
            validation=validation,
            explanations=sl_notes,
            invalidation_conditions=[],
        )

    liq_results = []
    struct_results = []
    for tf in cfg.liquidity_timeframes:
        b = bundles.get(tf)
        if b and b.liquidity is not None:
            liq_results.append(b.liquidity)
        if b and b.structure is not None:
            struct_results.append(b.structure)
    if setup_bundle.structure is not None and setup_bundle.structure not in struct_results:
        struct_results.append(setup_bundle.structure)
    if confirm_bundle.structure is not None:
        struct_results.append(confirm_bundle.structure)

    targets, tp_blockers = calculate_take_profits(
        direction=direction,
        entry=entry,
        stop=stop,
        liquidity_results=liq_results,
        structure_results=struct_results,
        opposing_ob_fvg=setup_bundle.ob_fvg,
        config=cfg,
    )
    if not targets:
        validation = validate_plan(
            eligibility=eligibility,
            direction=direction,
            entry=entry,
            stop=stop,
            targets=[],
            risk=None,
            sizing=None,
            market_type=market_type,
            config=cfg,
        )
        validation.blocking_reasons = _unique(validation.blocking_reasons + tp_blockers)
        validation.is_valid = False
        return TradePlanResult(
            **base_kwargs,  # type: ignore[arg-type]
            plan_status="blocked",
            entry=entry,
            stop_loss=stop,
            validation=validation,
            explanations=tp_blockers + sl_notes,
            invalidation_conditions=[stop.invalidation_explanation],
        )

    risk = calculate_risk_metrics(
        direction=direction,
        entry=entry,
        stop=stop,
        targets=targets,
        config=cfg,
    )
    sizing = calculate_position_sizing(
        entry=entry,
        stop=stop,
        account_balance=balance,
        risk_percent=risk_pct,
        market_type=market_type,
        config=cfg,
    )

    validation = validate_plan(
        eligibility=eligibility,
        direction=direction,
        entry=entry,
        stop=stop,
        targets=targets,
        risk=risk,
        sizing=sizing,
        market_type=market_type,
        config=cfg,
    )

    invalidation = [
        stop.invalidation_explanation,
        (
            f"Plan invalid if price closes beyond stop {stop.stop_loss_price:.6g} "
            f"({stop.stop_loss_source})."
        ),
    ]
    if direction == "bullish":
        invalidation.append("Bullish plan invalidates on confirmed breakdown below entry zone.")
    else:
        invalidation.append("Bearish plan invalidates on confirmed breakout above entry zone.")

    explanations = [
        f"Direction={direction} from confluence {confluence.preliminary_assessment.value} "
        f"({confluence.assessment_strength}).",
        entry.entry_explanation,
        stop.invalidation_explanation,
        f"Primary target {targets[0].label} @ {targets[0].price:.6g} "
        f"(RR {targets[0].risk_reward_ratio:.2f}).",
    ]
    explanations.extend(sl_notes)

    status = "eligible" if validation.is_valid else "invalid"

    return TradePlanResult(
        **base_kwargs,  # type: ignore[arg-type]
        plan_status=status,
        entry=entry,
        stop_loss=stop,
        take_profit_targets=targets,
        risk=risk,
        position_sizing=sizing,
        validation=validation,
        invalidation_conditions=invalidation,
        explanations=explanations + validation.warnings,
    )


def _data_quality(
    mtf: MultiTimeframeSnapshot,
    *,
    current_price: float | None,
    atr_available: bool,
) -> TradePlanDataQuality:
    used = [s.timeframe.value for s in mtf.timeframes if s.is_ready]
    unavailable = [t.value for t in mtf.unavailable_timeframes]
    stale = [
        s.timeframe.value
        for s in mtf.timeframes
        if s.is_stale or s.data_quality == "stale"
    ]
    limitations: list[str] = []
    if not atr_available:
        limitations.append("ATR unavailable on setup timeframe.")
    if current_price is None:
        limitations.append("Current price unavailable.")
    complete = mtf.overall_status == "ready" and current_price is not None
    return TradePlanDataQuality(
        overall=mtf.overall_status,
        is_analysis_complete=complete,
        timeframes_used=used,
        timeframes_unavailable=[str(x) for x in unavailable],
        timeframes_stale=stale,
        limitations=limitations,
        current_price=current_price,
        atr_available=atr_available,
    )


def _plan_id(
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    when: datetime,
    version: str,
) -> str:
    raw = f"{exchange.value}|{market_type.value}|{symbol.upper()}|{when.isoformat()}|{version}"
    return "tp_" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out
