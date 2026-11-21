"""Scanner persistence repository (Phase 5.5 Step 4).

Isolated from Phase 6.0.3 analysis tables. Soft-fails when persistence is
disabled or the database is unavailable — never claims success on failure.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.scanner import SCANNER_CONFIG_VERSION, MarketOpportunityRow, ScannerRun
from app.db.session import get_async_session_factory, is_persistence_active
from app.scanner.config import ScannerConfig
from app.scanner.identity import (
    append_status_history,
    compute_opportunity_id,
    compute_slot_key,
    content_hash_for_opportunity,
    fingerprint_from_opportunity,
    should_close_as_terminal,
)
from app.scanner.models import MarketOpportunity, ScanRunSummary

logger = get_logger(__name__)


def _as_decimal(value: float | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _tp_fields(opp: MarketOpportunity) -> dict[str, Any]:
    by = {t.label.upper(): t for t in opp.take_profits}
    out: dict[str, Any] = {}
    for i, key in enumerate(("tp1", "tp2", "tp3"), start=1):
        level = by.get(f"TP{i}")
        if level is None:
            out[key] = None
            out[f"{key}_available"] = False
        else:
            out[key] = _as_decimal(level.price) if level.available else None
            out[f"{key}_available"] = bool(level.available and level.price is not None)
    return out


def _config_snapshot(config: ScannerConfig) -> dict[str, Any]:
    return {
        "enabled": config.enabled,
        "scan_interval_seconds": config.scan_interval_seconds,
        "max_concurrent_per_exchange": config.max_concurrent_per_exchange,
        "max_pairs_per_market": config.max_pairs_per_market,
        "min_quote_volume_24h": config.min_quote_volume_24h,
        "ohlcv_cache_ttl_seconds": config.ohlcv_cache_ttl_seconds,
        "execution_timeframes": [tf.value for tf in config.execution_timeframes],
        "exchanges": [e.value for e in config.default_exchanges],
        "market_types": [m.value for m in config.default_market_types],
        "identity_version": "scanner-identity-v1",
    }


async def persist_scan_bundle(
    *,
    summary: ScanRunSummary,
    opportunities: list[MarketOpportunity],
    config: ScannerConfig,
    trigger: str = "manual",
) -> dict[str, Any]:
    """
    Persist a finished scan run + opportunity upserts.

    Returns a result dict. On disabled/unavailable DB: success=False, persisted=False.
    Never raises to callers for soft-fail paths (logs instead).
    """
    result: dict[str, Any] = {
        "success": False,
        "persisted": False,
        "reason": "",
        "scan_row_id": None,
        "upserted": 0,
        "inserted": 0,
        "updated": 0,
        "closed_superseded": 0,
    }
    if not is_persistence_active():
        result["reason"] = "persistence_disabled"
        return result

    factory = get_async_session_factory()
    if factory is None:
        result["reason"] = "session_factory_unavailable"
        return result

    try:
        async with factory() as session:
            async with session.begin():
                run = await _upsert_scanner_run(
                    session, summary=summary, config=config, trigger=trigger
                )
                result["scan_row_id"] = str(run.id)
                counts = {"upserted": 0, "inserted": 0, "updated": 0, "closed_superseded": 0}
                for opp in opportunities:
                    action = await _upsert_opportunity(
                        session,
                        opp=opp,
                        scan_run=run,
                        scan_id=summary.scan_id,
                    )
                    counts["upserted"] += 1
                    counts[action] += 1
                result.update(counts)
            result["success"] = True
            result["persisted"] = True
            result["reason"] = "ok"
            return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scanner persistence failed (soft): %s", exc)
        result["reason"] = f"db_error:{exc}"
        result["success"] = False
        result["persisted"] = False
        return result


async def _upsert_scanner_run(
    session: AsyncSession,
    *,
    summary: ScanRunSummary,
    config: ScannerConfig,
    trigger: str,
) -> ScannerRun:
    existing = await session.scalar(
        select(ScannerRun).where(ScannerRun.scan_id == summary.scan_id)
    )
    if existing is None:
        run = ScannerRun(
            scan_id=summary.scan_id,
            trigger=trigger,
            status=summary.status,
            started_at=summary.started_at,
            finished_at=summary.finished_at,
            duration_seconds=_as_decimal(summary.duration_seconds),
            exchanges=list(summary.exchanges),
            market_types=[m.value for m in config.default_market_types],
            execution_timeframes=[tf.value for tf in config.execution_timeframes],
            pairs_discovered=summary.pairs_discovered,
            pairs_eligible=summary.pairs_eligible,
            pairs_selected=summary.pairs_selected,
            pairs_scanned=summary.pairs_scanned,
            pairs_partial=summary.pairs_partial,
            pairs_failed=summary.pairs_failed,
            timeframe_analyses_attempted=summary.timeframe_analyses_attempted,
            timeframe_analyses_completed=summary.timeframe_analyses_completed,
            timeframe_analyses_failed=summary.timeframe_analyses_failed,
            opportunities_found=summary.opportunities_found,
            ready_count=summary.ready_count,
            long_count=summary.long_count,
            short_count=summary.short_count,
            ranking_method=summary.ranking_method or None,
            per_market=list(summary.per_market),
            excluded_sample=list(summary.excluded_pairs),
            errors=list(summary.errors),
            config_snapshot=_config_snapshot(config),
            config_version=SCANNER_CONFIG_VERSION,
        )
        session.add(run)
        await session.flush()
        return run

    existing.status = summary.status
    existing.finished_at = summary.finished_at
    existing.duration_seconds = _as_decimal(summary.duration_seconds)
    existing.pairs_discovered = summary.pairs_discovered
    existing.pairs_eligible = summary.pairs_eligible
    existing.pairs_selected = summary.pairs_selected
    existing.pairs_scanned = summary.pairs_scanned
    existing.pairs_partial = summary.pairs_partial
    existing.pairs_failed = summary.pairs_failed
    existing.timeframe_analyses_attempted = summary.timeframe_analyses_attempted
    existing.timeframe_analyses_completed = summary.timeframe_analyses_completed
    existing.timeframe_analyses_failed = summary.timeframe_analyses_failed
    existing.opportunities_found = summary.opportunities_found
    existing.ready_count = summary.ready_count
    existing.long_count = summary.long_count
    existing.short_count = summary.short_count
    existing.ranking_method = summary.ranking_method or None
    existing.per_market = list(summary.per_market)
    existing.excluded_sample = list(summary.excluded_pairs)
    existing.errors = list(summary.errors)
    await session.flush()
    return existing


async def _lock_slot(session: AsyncSession, slot_key: str) -> None:
    """Transaction-scoped advisory lock for concurrent generation allocation."""
    # hashtext is stable enough for advisory lock key space
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:slot))"),
        {"slot": slot_key},
    )


async def _upsert_opportunity(
    session: AsyncSession,
    *,
    opp: MarketOpportunity,
    scan_run: ScannerRun,
    scan_id: str,
) -> str:
    """
    Upsert one opportunity. Returns action: inserted | updated | closed_superseded
    (closed_superseded means prior open closed + new inserted — counted as inserted
    by caller via separate bump; here return 'inserted' after supersede for simplicity
    but we return 'closed_superseded' when that path runs).
    """
    now = datetime.now(timezone.utc)
    slot_key = compute_slot_key(
        opp.exchange, opp.market_type, opp.symbol, opp.timeframe
    )
    fingerprint = fingerprint_from_opportunity(opp)
    status_s = opp.status.value if hasattr(opp.status, "value") else str(opp.status)
    direction_s = (
        opp.direction.value if opp.direction is not None else None
    )
    await _lock_slot(session, slot_key)

    open_row = await session.scalar(
        select(MarketOpportunityRow)
        .where(
            MarketOpportunityRow.slot_key == slot_key,
            MarketOpportunityRow.is_open.is_(True),
        )
        .with_for_update()
    )

    # Same open structural setup → update in place
    if open_row is not None and open_row.setup_fingerprint == fingerprint:
        return await _update_open_row(
            session,
            row=open_row,
            opp=opp,
            scan_run=scan_run,
            scan_id=scan_id,
            fingerprint=fingerprint,
            status_s=status_s,
            direction_s=direction_s,
            now=now,
        )

    # New structural setup while an open row exists → close without false terminal
    closed_superseded = False
    if open_row is not None and open_row.setup_fingerprint != fingerprint:
        open_row.is_open = False
        # Do NOT set INVALIDATED/EXPIRED — preserve last engine-derived status
        meta = dict(open_row.metadata_json or {})
        meta["closed_reason"] = "superseded_by_new_generation"
        meta["superseded_at"] = now.isoformat()
        open_row.metadata_json = meta
        open_row.status_history = append_status_history(
            list(open_row.status_history or []),
            at_iso=now.isoformat(),
            from_status=open_row.status,
            to_status=open_row.status,
            scan_id=scan_id,
            note="closed_open_slot_for_new_generation",
        )
        open_row.last_evaluated_at = now
        open_row.updated_at = now
        await session.flush()
        closed_superseded = True

    # Allocate next generation under lock
    max_gen = await session.scalar(
        select(MarketOpportunityRow.setup_generation)
        .where(MarketOpportunityRow.slot_key == slot_key)
        .order_by(MarketOpportunityRow.setup_generation.desc())
        .limit(1)
        .with_for_update()
    )
    generation = int(max_gen or 0) + 1
    opportunity_id = compute_opportunity_id(slot_key, generation, fingerprint)
    chash = content_hash_for_opportunity(opp, setup_fingerprint=fingerprint)
    tp = _tp_fields(opp)
    is_open = not should_close_as_terminal(status_s)

    row = MarketOpportunityRow(
        opportunity_id=opportunity_id,
        slot_key=slot_key,
        setup_fingerprint=fingerprint,
        setup_generation=generation,
        is_open=is_open,
        exchange=opp.exchange.value,
        market_type=opp.market_type.value,
        symbol=opp.symbol,
        execution_timeframe=opp.timeframe.value,
        direction=direction_s,
        decision=opp.decision,
        decision_reason=opp.decision_reason or None,
        status=status_s,
        previous_status=None,
        status_changed_at=now,
        status_history=append_status_history(
            [],
            at_iso=now.isoformat(),
            from_status=None,
            to_status=status_s,
            scan_id=scan_id,
            note="created",
        ),
        engine_lifecycle=opp.lifecycle,
        current_price=_as_decimal(opp.current_price),
        price_updated_at=opp.price_updated_at,
        price_source=opp.price_source,
        entry_reference=_as_decimal(opp.entry_reference),
        entry_low=_as_decimal(opp.entry_low),
        entry_high=_as_decimal(opp.entry_high),
        stop_loss=_as_decimal(opp.stop_loss),
        tp1=tp["tp1"],
        tp2=tp["tp2"],
        tp3=tp["tp3"],
        tp1_available=tp["tp1_available"],
        tp2_available=tp["tp2_available"],
        tp3_available=tp["tp3_available"],
        primary_rr=_as_decimal(opp.primary_rr),
        confluence_score=_as_decimal(opp.confluence_score),
        confluence_bullish=_as_decimal(opp.confluence_bullish),
        confluence_bearish=_as_decimal(opp.confluence_bearish),
        entry_distance_pct=_as_decimal(opp.entry_distance_pct),
        quote_volume_24h=_as_decimal(opp.quote_volume_24h),
        actionable=bool(opp.actionable),
        supporting_evidence=list(opp.supporting_evidence),
        blocking_conditions=list(opp.blocking_conditions),
        invalidation_reason=(
            opp.decision_reason if status_s == "INVALIDATED" else None
        ),
        expiration_reason=opp.decision_reason if status_s == "EXPIRED" else None,
        decision_id=opp.decision_id,
        trade_plan_id=opp.trade_plan_id,
        analysis_timestamp=opp.analysis_timestamp,
        first_detected_at=now,
        last_evaluated_at=now,
        last_scan_run_id=scan_run.id,
        rank_score=_as_decimal(opp.rank_score),
        rank_explanation=opp.rank_explanation or None,
        content_hash=chash,
        metadata_json={
            **(opp.metadata or {}),
            "slot_key": slot_key,
            "setup_fingerprint": fingerprint,
            "setup_generation": generation,
        },
        planned_not_fills_note=opp.planned_not_fills_note,
    )
    # Reflect stable id back onto in-memory object for this process
    opp.opportunity_id = opportunity_id
    opp.metadata = {
        **(opp.metadata or {}),
        "slot_key": slot_key,
        "setup_fingerprint": fingerprint,
        "setup_generation": generation,
    }
    session.add(row)
    await session.flush()
    return "closed_superseded" if closed_superseded else "inserted"


async def _update_open_row(
    session: AsyncSession,
    *,
    row: MarketOpportunityRow,
    opp: MarketOpportunity,
    scan_run: ScannerRun,
    scan_id: str,
    fingerprint: str,
    status_s: str,
    direction_s: str | None,
    now: datetime,
) -> str:
    prev_status = row.status
    chash = content_hash_for_opportunity(opp, setup_fingerprint=fingerprint)
    tp = _tp_fields(opp)

    if prev_status != status_s:
        row.previous_status = prev_status
        row.status_changed_at = now
        row.status_history = append_status_history(
            list(row.status_history or []),
            at_iso=now.isoformat(),
            from_status=prev_status,
            to_status=status_s,
            scan_id=scan_id,
        )

    row.status = status_s
    row.direction = direction_s
    row.decision = opp.decision
    row.decision_reason = opp.decision_reason or None
    row.engine_lifecycle = opp.lifecycle
    row.current_price = _as_decimal(opp.current_price)
    row.price_updated_at = opp.price_updated_at
    row.price_source = opp.price_source
    row.entry_reference = _as_decimal(opp.entry_reference)
    row.entry_low = _as_decimal(opp.entry_low)
    row.entry_high = _as_decimal(opp.entry_high)
    row.stop_loss = _as_decimal(opp.stop_loss)
    row.tp1 = tp["tp1"]
    row.tp2 = tp["tp2"]
    row.tp3 = tp["tp3"]
    row.tp1_available = tp["tp1_available"]
    row.tp2_available = tp["tp2_available"]
    row.tp3_available = tp["tp3_available"]
    row.primary_rr = _as_decimal(opp.primary_rr)
    row.confluence_score = _as_decimal(opp.confluence_score)
    row.confluence_bullish = _as_decimal(opp.confluence_bullish)
    row.confluence_bearish = _as_decimal(opp.confluence_bearish)
    row.entry_distance_pct = _as_decimal(opp.entry_distance_pct)
    row.quote_volume_24h = _as_decimal(opp.quote_volume_24h)
    row.actionable = bool(opp.actionable)
    row.supporting_evidence = list(opp.supporting_evidence)
    row.blocking_conditions = list(opp.blocking_conditions)
    row.decision_id = opp.decision_id
    row.trade_plan_id = opp.trade_plan_id
    row.analysis_timestamp = opp.analysis_timestamp
    row.last_evaluated_at = now
    row.last_scan_run_id = scan_run.id
    row.rank_score = _as_decimal(opp.rank_score)
    row.rank_explanation = opp.rank_explanation or None
    row.content_hash = chash
    row.updated_at = now

    if should_close_as_terminal(status_s):
        row.is_open = False
        if status_s == "INVALIDATED":
            row.invalidation_reason = opp.decision_reason or row.invalidation_reason
        if status_s == "EXPIRED":
            row.expiration_reason = opp.decision_reason or row.expiration_reason

    opp.opportunity_id = row.opportunity_id
    opp.metadata = {
        **(opp.metadata or {}),
        "slot_key": row.slot_key,
        "setup_fingerprint": fingerprint,
        "setup_generation": row.setup_generation,
    }
    await session.flush()
    return "updated"
