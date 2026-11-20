"""5M entry confirmation from confirmed closed-candle evidence (Phase 4.4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.analysis.confluence.engine import TimeframeAnalysisBundle
from app.analysis.decision_engine.config import DecisionConfig
from app.analysis.decision_engine.models import EntryConfirmationResult
from app.analysis.liquidity.models import LiquidityType, ReactionHint
from app.analysis.market_structure.models import StructureDirection
from app.exchanges.types import Candle, Timeframe


def evaluate_entry_confirmation(
    *,
    direction: str,
    confirm_bundle: TimeframeAnalysisBundle | None,
    confirm_candles: list[Candle],
    as_of: datetime,
    config: DecisionConfig,
) -> EntryConfirmationResult:
    if confirm_bundle is None:
        return EntryConfirmationResult(
            status="unavailable",
            explanation="5M confirmation analysis unavailable.",
            blocking_reasons=["5M analysis bundle missing."],
        )

    closed = [c for c in confirm_candles if c.is_closed]
    if not closed:
        return EntryConfirmationResult(
            status="unavailable",
            explanation="No closed 5M candles available for confirmation.",
            blocking_reasons=["5M closed candles missing."],
        )

    latest_closed = closed[-1].timestamp
    max_age = _candle_window(closed, config.max_confirmation_age_candles)
    want = StructureDirection.BULLISH if direction == "bullish" else StructureDirection.BEARISH

    candidates: list[tuple[float, str, str, str, datetime]] = []
    # (priority, type, event_key, explanation, ts)

    structure = confirm_bundle.structure
    if structure is not None:
        for mss in structure.mss_events:
            if mss.direction != want:
                continue
            ts = mss.confirmation_timestamp or mss.candle_timestamp
            if not _within(ts, max_age, as_of):
                continue
            candidates.append(
                (
                    1.0,
                    "mss",
                    mss.event_key,
                    f"5M confirmed MSS ({mss.direction.value}).",
                    ts,
                )
            )
        for bos in structure.bos_events:
            if bos.direction != want:
                continue
            ts = bos.confirmation_timestamp or bos.candle_timestamp
            if not _within(ts, max_age, as_of):
                continue
            candidates.append(
                (
                    0.9,
                    "bos",
                    bos.event_key,
                    f"5M confirmed BOS ({bos.direction.value}).",
                    ts,
                )
            )

    liquidity = confirm_bundle.liquidity
    if liquidity is not None:
        for sweep in liquidity.sweeps:
            if not sweep.confirmed:
                continue
            hint = sweep.reaction_hint
            if hint is None:
                continue
            if direction == "bullish" and hint != ReactionHint.BULLISH:
                continue
            if direction == "bearish" and hint != ReactionHint.BEARISH:
                continue
            # SSL sweep → bullish hint; BSL → bearish hint (Phase 3.3.1)
            if direction == "bullish" and sweep.liquidity_type != LiquidityType.SSL:
                continue
            if direction == "bearish" and sweep.liquidity_type != LiquidityType.BSL:
                continue
            ts = sweep.confirmation_timestamp or sweep.candle_timestamp
            if not _within(ts, max_age, as_of):
                continue
            candidates.append(
                (
                    0.85,
                    "liquidity_sweep",
                    sweep.event_key,
                    (
                        f"5M confirmed {sweep.liquidity_type.value.upper()} sweep "
                        f"→ reaction_hint={hint.value} (contextual confirmation)."
                    ),
                    ts,
                )
            )

    # Deduplicate by event_key; prefer higher priority then newer timestamp
    candidates.sort(key=lambda x: (-x[0], -x[4].timestamp()))
    seen: set[str] = set()
    unique: list[tuple[float, str, str, str, datetime]] = []
    for item in candidates:
        if item[2] in seen:
            continue
        seen.add(item[2])
        unique.append(item)

    if not unique:
        return EntryConfirmationResult(
            status="not_confirmed",
            is_confirmed=False,
            timeframe=Timeframe.M5.value,
            direction=direction,
            explanation=(
                f"No confirmed 5M {direction} entry confirmation within the last "
                f"{config.max_confirmation_age_candles} closed candles "
                f"(latest closed {latest_closed.isoformat()})."
            ),
            blocking_reasons=["5M entry confirmation not present."],
        )

    best = unique[0]
    return EntryConfirmationResult(
        status="confirmed",
        is_confirmed=True,
        confirmation_type=best[1],
        source_event_key=best[2],
        timeframe=Timeframe.M5.value,
        direction=direction,
        explanation=best[3],
        evidence_ids=[f"confirm:{best[1]}:{best[2]}"],
    )


def _candle_window(closed: list[Candle], n: int) -> datetime:
    idx = max(0, len(closed) - n)
    return closed[idx].timestamp


def _within(ts: datetime | None, earliest: datetime, as_of: datetime) -> bool:
    if ts is None:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if earliest.tzinfo is None:
        earliest = earliest.replace(tzinfo=timezone.utc)
    return earliest <= ts <= as_of + timedelta(seconds=1)
