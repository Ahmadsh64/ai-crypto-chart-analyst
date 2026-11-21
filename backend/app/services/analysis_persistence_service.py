"""Soft-fail live Analyze → Supabase persistence (Phase 6.0.3).

Never changes deterministic Decision / Trade Plan / snapshot math.
Never raises into Analyze routes for DB failures.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

from app.api.schemas.decision import DecisionResponse
from app.api.schemas.trade_plan import TradePlanResponse
from app.core.logging import get_logger
from app.db.exceptions import (
    IdempotencyConflictError,
    PersistenceDisabledError,
    PersistenceUnavailableError,
)
from app.db.identity import new_analysis_run_id
from app.db.repositories.analysis import persist_analysis_bundle
from app.db.session import is_persistence_active
from app.db.ssl_config import sanitize_tls_error_text
from app.exchanges.types import ExchangeId, MarketType

logger = get_logger(__name__)

PersistenceStatus = Literal[
    "disabled",
    "saved",
    "idempotent",
    "failed",
    "conflict",
]


class PersistenceStatusCode(str, Enum):
    DISABLED = "disabled"
    SAVED = "saved"
    IDEMPOTENT = "idempotent"
    FAILED = "failed"
    CONFLICT = "conflict"


@dataclass(slots=True)
class LivePersistOutcome:
    status: PersistenceStatus
    analysis_run_id: str
    snapshot_id: str | None
    analysis_session_id: str | None
    consistency_status: str | None
    detail: str | None
    correlation_id: str


def flatten_decision_for_persist(decision: DecisionResponse) -> dict[str, Any]:
    """Map DecisionResponse into persist_analysis_bundle extract shape."""
    d = decision.model_dump(mode="json")
    zone = d.get("entry_zone_summary") or {}
    if isinstance(zone, dict):
        d.setdefault(
            "entry_reference_price",
            zone.get("entry_reference_price") or zone.get("reference_price"),
        )
        d.setdefault("entry_low", zone.get("entry_low") or zone.get("low"))
        d.setdefault("entry_high", zone.get("entry_high") or zone.get("high"))
    scores = d.get("confluence_scores") or {}
    if isinstance(scores, dict):
        d["bullish_score"] = scores.get("bullish_score")
        d["bearish_score"] = scores.get("bearish_score")
    d["evidence"] = d.get("supporting_evidence") or []
    d["conflicts"] = d.get("conflict_ids") or []
    return d


def flatten_trade_plan_for_persist(plan: TradePlanResponse) -> dict[str, Any]:
    """Map TradePlanResponse into persist_analysis_bundle extract shape."""
    p = plan.model_dump(mode="json")
    entry = p.get("entry") or {}
    if isinstance(entry, dict):
        p["entry_reference_price"] = entry.get("entry_reference_price")
        p["entry_low"] = entry.get("entry_low")
        p["entry_high"] = entry.get("entry_high")
        if not p.get("timeframe"):
            p["timeframe"] = entry.get("timeframe")
    sl = p.get("stop_loss") or {}
    if isinstance(sl, dict):
        p["stop_loss_price"] = sl.get("stop_loss_price")
    tps = p.get("take_profit_targets") or []
    prices: list[Any] = []
    for t in tps:
        if isinstance(t, dict) and t.get("price") is not None:
            prices.append(t["price"])
    p["take_profit_prices"] = prices
    p["take_profit_targets"] = prices
    if tps and isinstance(tps[0], dict) and p.get("primary_rr") is None:
        p["primary_rr"] = tps[0].get("risk_reward_ratio")
    risk = p.get("risk") or {}
    if isinstance(risk, dict) and p.get("primary_rr") is None:
        # keep None if absent
        pass
    p["eligibility_payload"] = p.get("eligibility") or {}
    return p


async def persist_live_analyze_bundle(
    *,
    exchange: ExchangeId | str,
    market_type: MarketType | str,
    symbol: str,
    decision: DecisionResponse,
    trade_plan: TradePlanResponse,
    timeframe: str | None = None,
    data_freshness: str | None = None,
    analysis_run_id: str | None = None,
    session_source: str = "live_market",
    snapshot_kind: str = "live_decision_bundle",
) -> LivePersistOutcome:
    """
    Persist one Analyze orchestration soft-fail.

    Always allocates/preserves a stable analysis_run_id for correlation.
    Never raises; never mutates decision/trade_plan.
    """
    run_id = analysis_run_id or new_analysis_run_id()
    correlation_id = run_id

    if not is_persistence_active():
        return LivePersistOutcome(
            status="disabled",
            analysis_run_id=run_id,
            snapshot_id=None,
            analysis_session_id=None,
            consistency_status=None,
            detail="Persistence disabled",
            correlation_id=correlation_id,
        )

    decision_payload = flatten_decision_for_persist(decision)
    plan_payload = flatten_trade_plan_for_persist(trade_plan)
    config_versions = {
        "decision": decision.configuration_version,
        "trade_plan": trade_plan.configuration_version,
    }
    freshness = data_freshness
    if freshness is None and decision.data_quality is not None:
        freshness = (
            "LIVE"
            if decision.data_quality.is_analysis_complete
            else "PARTIAL"
        )

    try:
        result = await persist_analysis_bundle(
            exchange=str(exchange.value if hasattr(exchange, "value") else exchange),
            market_type=str(
                market_type.value if hasattr(market_type, "value") else market_type
            ),
            symbol=symbol,
            decision=decision_payload,
            trade_plan=plan_payload,
            analysis_run_id=run_id,
            timeframe=timeframe
            or getattr(decision, "timeframe", None)
            or (plan_payload.get("timeframe") if isinstance(plan_payload, dict) else None),
            snapshot_kind=snapshot_kind,
            configuration_versions=config_versions,
            data_freshness=freshness,
            ensure_analysis_session=True,
            session_source=session_source,
        )
        status: PersistenceStatus = "idempotent" if result.idempotent else "saved"
        return LivePersistOutcome(
            status=status,
            analysis_run_id=result.analysis_run_id,
            snapshot_id=str(result.snapshot_id),
            analysis_session_id=(
                str(result.analysis_session_id)
                if result.analysis_session_id
                else None
            ),
            consistency_status=result.consistency_status,
            detail=None,
            correlation_id=correlation_id,
        )
    except PersistenceDisabledError:
        return LivePersistOutcome(
            status="disabled",
            analysis_run_id=run_id,
            snapshot_id=None,
            analysis_session_id=None,
            consistency_status=None,
            detail="Persistence disabled",
            correlation_id=correlation_id,
        )
    except IdempotencyConflictError as exc:
        logger.warning(
            "Analyze persistence conflict correlation_id=%s code=%s",
            correlation_id,
            exc.code,
        )
        return LivePersistOutcome(
            status="conflict",
            analysis_run_id=run_id,
            snapshot_id=None,
            analysis_session_id=None,
            consistency_status=None,
            detail="History conflict — analysis not overwritten",
            correlation_id=correlation_id,
        )
    except PersistenceUnavailableError as exc:
        logger.warning(
            "Analyze persistence unavailable correlation_id=%s detail=%s",
            correlation_id,
            sanitize_tls_error_text(str(exc)),
        )
        return LivePersistOutcome(
            status="failed",
            analysis_run_id=run_id,
            snapshot_id=None,
            analysis_session_id=None,
            consistency_status=None,
            detail="History saving unavailable",
            correlation_id=correlation_id,
        )
    except Exception as exc:  # noqa: BLE001 — Analyze must not fail
        logger.warning(
            "Analyze persistence failed correlation_id=%s type=%s detail=%s",
            correlation_id,
            type(exc).__name__,
            sanitize_tls_error_text(str(exc)),
        )
        return LivePersistOutcome(
            status="failed",
            analysis_run_id=run_id,
            snapshot_id=None,
            analysis_session_id=None,
            consistency_status=None,
            detail="History saving unavailable",
            correlation_id=correlation_id,
        )
