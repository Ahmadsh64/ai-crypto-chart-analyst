"""Decimal-safe JSONB serialization and canonical hashing (Phase 6.0.2)."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID


def decimal_to_str(value: Decimal | int | float | str | None) -> str | None:
    """Normalize a financial value to a non-scientific decimal string."""
    if value is None:
        return None
    if isinstance(value, str):
        d = Decimal(value)
    elif isinstance(value, Decimal):
        d = value
    elif isinstance(value, bool):
        raise TypeError("bool is not a financial decimal")
    elif isinstance(value, int):
        d = Decimal(value)
    elif isinstance(value, float):
        # Avoid binary float drift: use exact repr then Decimal
        d = Decimal(str(value))
    else:
        d = Decimal(str(value))
    normalized = format(d, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized if normalized else "0"


def _to_utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    text = dt.isoformat().replace("+00:00", "Z")
    return text


def jsonable(value: Any) -> Any:
    """Convert value tree so JSONB stores decimals as strings (no floats)."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return decimal_to_str(value)
    if isinstance(value, Decimal):
        return decimal_to_str(value)
    if isinstance(value, datetime):
        return _to_utc_iso(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if hasattr(value, "model_dump"):
        return jsonable(value.model_dump(mode="python"))
    return value


def canonical_json_bytes(value: Any) -> bytes:
    """UTF-8 canonical JSON: sorted keys, no whitespace, decimal strings."""
    prepared = jsonable(value)
    return json.dumps(
        prepared,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_hash(value: Any) -> str:
    """SHA-256 hex of canonical JSON bytes."""
    return sha256_hex(canonical_json_bytes(value))
