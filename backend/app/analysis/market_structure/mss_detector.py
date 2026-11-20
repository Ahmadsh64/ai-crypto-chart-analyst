"""Market Structure Shift (MSS) — CHoCH + ATR displacement confirmation."""

from __future__ import annotations

import math

from app.analysis.market_structure.config import MarketStructureConfig
from app.analysis.market_structure.models import CHoCHEvent, MSSEvent, StructureBreak
from app.analysis.market_structure.bos_detector import break_event_key
from app.exchanges.types import Candle


def has_displacement(
    candle: Candle,
    atr_value: float | None,
    config: MarketStructureConfig,
) -> tuple[bool, float, float | None]:
    """
    Displacement: candle body >= displacement_atr_mult × ATR(period).

    If ATR is missing / non-finite, displacement is False and no MSS is emitted.
    Never invents ATR.
    """
    body = abs(float(candle.close) - float(candle.open))
    if atr_value is None or not math.isfinite(atr_value) or atr_value <= 0:
        return False, body, None
    threshold = config.displacement_atr_mult * float(atr_value)
    return body >= threshold, body, float(atr_value)


def build_mss_from_choch(
    choch: CHoCHEvent,
    break_event: StructureBreak,
    candle: Candle,
    body: float,
    atr_value: float,
    config: MarketStructureConfig,
) -> MSSEvent:
    key = break_event_key(
        "mss",
        choch.direction,
        choch.symbol,
        choch.timeframe.value,
        # reuse broken swing confirmation path via choch key suffix uniqueness
        choch.candle_timestamp,
        candle.timestamp,
    )
    return MSSEvent(
        event_key=key,
        exchange=choch.exchange,
        symbol=choch.symbol,
        market_type=choch.market_type,
        timeframe=choch.timeframe,
        direction=choch.direction,
        choch_event_key=choch.event_key,
        broken_level=choch.broken_level,
        close_price=float(candle.close),
        candle_timestamp=candle.timestamp,
        confirmation_timestamp=candle.timestamp,
        body_size=body,
        atr_value=atr_value,
        displacement_mult=config.displacement_atr_mult,
        previous_bias=choch.previous_bias,
        new_bias=choch.new_bias,
        config_version=config.config_version,
    )
