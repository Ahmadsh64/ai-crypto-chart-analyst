"""Fee amount calculations (Phase 5.2.3)."""

from __future__ import annotations

from decimal import Decimal

from app.replay.costs.config import FeeSchedule
from app.replay.costs.enums import MakerTakerClass, MakerTakerFallback


def applicable_fee_rate(
    classification: MakerTakerClass,
    schedule: FeeSchedule,
    *,
    fallback: MakerTakerFallback,
) -> tuple[Decimal, MakerTakerClass, list[str]]:
    """Return (rate, effective_class, warnings)."""
    warnings: list[str] = []
    if classification == "maker":
        return schedule.maker_fee_rate, "maker", warnings
    if classification == "taker":
        return schedule.taker_fee_rate, "taker", warnings

    if fallback == "assume_taker":
        warnings.append(
            "Maker/taker unknown from OHLCV; applied assume_taker fallback (estimated)."
        )
        return schedule.taker_fee_rate, "taker", warnings
    if fallback == "assume_maker":
        warnings.append(
            "Maker/taker unknown from OHLCV; applied assume_maker fallback (estimated)."
        )
        return schedule.maker_fee_rate, "maker", warnings
    warnings.append("Maker/taker unknown; fee rate unresolved — using taker rate as placeholder.")
    return schedule.taker_fee_rate, "unknown", warnings


def calculate_fee(notional: Decimal, fee_rate: Decimal) -> Decimal:
    return (notional * fee_rate).quantize(Decimal("0.00000001"))
