"""Stable opportunity identity for Phase 5.5 scanner persistence.

Fingerprint composition (structural only)
-----------------------------------------
Includes:
  - decision (LONG/SHORT/WAIT/NO TRADE)
  - direction when present
  - planned entry_low / entry_high / entry_reference
  - planned stop_loss
  - TP1–TP3 prices only when marked available
  - primary_rr when present (canonical plan characteristic)

Excludes (volatile / non-structural):
  - decision_id, trade_plan_id (not verified stable across rescans)
  - analysis timestamps, scan ids, price timestamps
  - current market price, confluence scores, rank scores
  - lifecycle / opportunity status alone
  - supporting_evidence / blocking_conditions text

Lifecycle status changes alone MUST NOT change the fingerprint or generation.
Terminal INVALIDATED/EXPIRED are applied only from engine lifecycle evidence,
never merely because a new fingerprint appeared.

Supersede policy
----------------
If an open row's fingerprint differs from the new structural fingerprint,
close the open row with is_open=false WITHOUT forcing INVALIDATED/EXPIRED.
Record closed_reason=superseded_by_new_generation in metadata/history.
A new setup_generation + opportunity_id is allocated for the new fingerprint.

Capped status_history (max 20) is not an unbounded immutable audit log.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal, InvalidOperation
from typing import Any

from app.exchanges.types import ExchangeId, MarketType, Timeframe

STATUS_HISTORY_MAX = 20
TERMINAL_STATUSES = frozenset({"INVALIDATED", "EXPIRED"})
CONFIG_VERSION = "scanner-identity-v1"


def _norm_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _dec_token(value: float | Decimal | None) -> str:
    if value is None:
        return ""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return ""
    # Normalize: no exponent, trim trailing zeros for stable hashing
    normalized = d.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def compute_slot_key(
    exchange: ExchangeId | str,
    market_type: MarketType | str,
    symbol: str,
    execution_timeframe: Timeframe | str,
) -> str:
    ex = exchange.value if isinstance(exchange, ExchangeId) else str(exchange)
    mt = market_type.value if isinstance(market_type, MarketType) else str(market_type)
    tf = (
        execution_timeframe.value
        if isinstance(execution_timeframe, Timeframe)
        else str(execution_timeframe)
    )
    raw = f"{ex}:{mt}:{_norm_symbol(symbol)}:{tf}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def compute_setup_fingerprint(
    *,
    decision: str | None,
    direction: str | None = None,
    entry_low: float | None = None,
    entry_high: float | None = None,
    entry_reference: float | None = None,
    stop_loss: float | None = None,
    tp1: float | None = None,
    tp1_available: bool = False,
    tp2: float | None = None,
    tp2_available: bool = False,
    tp3: float | None = None,
    tp3_available: bool = False,
    primary_rr: float | None = None,
) -> str:
    """
    Structural fingerprint for setup identity.

    Intentionally ignores decision_id, trade_plan_id, timestamps, lifecycle,
    confluence, and current price.
    """
    parts = [
        f"decision={(decision or '').strip().upper()}",
        f"direction={(direction or '').strip().upper()}",
        f"entry_low={_dec_token(entry_low)}",
        f"entry_high={_dec_token(entry_high)}",
        f"entry_ref={_dec_token(entry_reference)}",
        f"stop={_dec_token(stop_loss)}",
        f"tp1={_dec_token(tp1) if tp1_available else ''}",
        f"tp2={_dec_token(tp2) if tp2_available else ''}",
        f"tp3={_dec_token(tp3) if tp3_available else ''}",
        f"rr={_dec_token(primary_rr)}",
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def compute_opportunity_id(
    slot_key: str,
    setup_generation: int,
    setup_fingerprint: str,
) -> str:
    raw = f"{slot_key}:{int(setup_generation)}:{setup_fingerprint}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def fingerprint_from_opportunity(opp: Any) -> str:
    """Build fingerprint from a MarketOpportunity-like object."""
    tps = list(getattr(opp, "take_profits", None) or [])
    by_label = {str(getattr(t, "label", "")).upper(): t for t in tps}

    def _tp(label: str) -> tuple[float | None, bool]:
        level = by_label.get(label)
        if level is None:
            return None, False
        return getattr(level, "price", None), bool(getattr(level, "available", False))

    tp1, tp1_ok = _tp("TP1")
    tp2, tp2_ok = _tp("TP2")
    tp3, tp3_ok = _tp("TP3")
    direction = getattr(opp, "direction", None)
    direction_s = direction.value if hasattr(direction, "value") else direction
    return compute_setup_fingerprint(
        decision=getattr(opp, "decision", None),
        direction=direction_s,
        entry_low=getattr(opp, "entry_low", None),
        entry_high=getattr(opp, "entry_high", None),
        entry_reference=getattr(opp, "entry_reference", None),
        stop_loss=getattr(opp, "stop_loss", None),
        tp1=tp1,
        tp1_available=tp1_ok,
        tp2=tp2,
        tp2_available=tp2_ok,
        tp3=tp3,
        tp3_available=tp3_ok,
        primary_rr=getattr(opp, "primary_rr", None),
    )


def content_hash_for_opportunity(opp: Any, *, setup_fingerprint: str) -> str:
    """Hash of persisted analytical fields (excludes volatile price/timestamps)."""
    status = getattr(opp, "status", None)
    status_s = status.value if hasattr(status, "value") else str(status or "")
    payload = "|".join(
        [
            setup_fingerprint,
            status_s,
            str(getattr(opp, "actionable", False)),
            _dec_token(getattr(opp, "confluence_score", None)),
            (getattr(opp, "decision_reason", None) or "")[:200],
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def append_status_history(
    history: list[dict[str, Any]] | None,
    *,
    at_iso: str,
    from_status: str | None,
    to_status: str,
    scan_id: str | None,
    note: str | None = None,
    max_len: int = STATUS_HISTORY_MAX,
) -> list[dict[str, Any]]:
    """Append one transition; cap at max_len (not an unbounded audit log)."""
    out = list(history or [])
    event: dict[str, Any] = {
        "at": at_iso,
        "from": from_status,
        "to": to_status,
        "scan_id": scan_id,
    }
    if note:
        event["note"] = note
    out.append(event)
    if len(out) > max_len:
        out = out[-max_len:]
    return out


def is_terminal_status(status: str | None) -> bool:
    return (status or "") in TERMINAL_STATUSES


def should_close_as_terminal(opportunity_status: str) -> bool:
    """
    Close is_open when status is engine-derived INVALIDATED/EXPIRED.

    Do NOT use this path for fingerprint supersede — that closes without
    relabeling status as INVALIDATED/EXPIRED.
    """
    return is_terminal_status(opportunity_status)
