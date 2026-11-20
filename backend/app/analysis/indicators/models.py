"""Indicator result models and registry metadata."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class IndicatorStatus(str, Enum):
    READY = "ready"
    WARMING_UP = "warming_up"
    INSUFFICIENT_DATA = "insufficient_data"
    ERROR = "error"


class IndicatorId(str, Enum):
    EMA_9 = "ema_9"
    EMA_20 = "ema_20"
    EMA_50 = "ema_50"
    EMA_100 = "ema_100"
    EMA_200 = "ema_200"
    SMA_20 = "sma_20"
    SMA_50 = "sma_50"
    SMA_200 = "sma_200"
    RSI_14 = "rsi_14"
    MACD = "macd"
    STOCH_RSI = "stoch_rsi"
    ATR_14 = "atr_14"
    BOLLINGER = "bollinger"
    VOLUME_SMA_20 = "volume_sma_20"
    OBV = "obv"
    RELATIVE_VOLUME = "relative_volume"


# Minimum closed candles required before status becomes "ready"
WARMUP_REQUIREMENTS: dict[IndicatorId, int] = {
    IndicatorId.EMA_9: 9,
    IndicatorId.EMA_20: 20,
    IndicatorId.EMA_50: 50,
    IndicatorId.EMA_100: 100,
    IndicatorId.EMA_200: 200,
    IndicatorId.SMA_20: 20,
    IndicatorId.SMA_50: 50,
    IndicatorId.SMA_200: 200,
    IndicatorId.RSI_14: 15,
    IndicatorId.MACD: 35,  # EMA26 + signal EMA9
    IndicatorId.STOCH_RSI: 17,  # RSI14 + stoch14 + smooth3 (conservative)
    IndicatorId.ATR_14: 15,
    IndicatorId.BOLLINGER: 20,
    IndicatorId.VOLUME_SMA_20: 20,
    IndicatorId.OBV: 2,
    IndicatorId.RELATIVE_VOLUME: 20,
}

INDICATOR_PARAMS: dict[IndicatorId, dict[str, Any]] = {
    IndicatorId.EMA_9: {"period": 9, "source": "close"},
    IndicatorId.EMA_20: {"period": 20, "source": "close"},
    IndicatorId.EMA_50: {"period": 50, "source": "close"},
    IndicatorId.EMA_100: {"period": 100, "source": "close"},
    IndicatorId.EMA_200: {"period": 200, "source": "close"},
    IndicatorId.SMA_20: {"period": 20, "source": "close"},
    IndicatorId.SMA_50: {"period": 50, "source": "close"},
    IndicatorId.SMA_200: {"period": 200, "source": "close"},
    IndicatorId.RSI_14: {"period": 14, "source": "close", "method": "wilder"},
    IndicatorId.MACD: {"fast": 12, "slow": 26, "signal": 9, "source": "close"},
    IndicatorId.STOCH_RSI: {"rsi_period": 14, "stoch_period": 14, "k_smooth": 3, "d_smooth": 3},
    IndicatorId.ATR_14: {"period": 14, "method": "wilder"},
    IndicatorId.BOLLINGER: {"period": 20, "std_dev": 2.0, "source": "close"},
    IndicatorId.VOLUME_SMA_20: {"period": 20},
    IndicatorId.OBV: {},
    IndicatorId.RELATIVE_VOLUME: {"period": 20},
}

DEFAULT_INDICATORS: tuple[IndicatorId, ...] = tuple(IndicatorId)


class IndicatorPoint(BaseModel):
    """Single timestamp-aligned indicator observation. Missing values stay null."""

    timestamp: datetime
    values: dict[str, float | None]
    is_closed: bool = True


class IndicatorLatest(BaseModel):
    """Latest value(s) for dashboard widgets."""

    status: IndicatorStatus
    is_forming: bool = False
    timestamp: datetime | None = None
    warmup_required: int
    samples_used: int
    params: dict[str, Any] = Field(default_factory=dict)
    # Scalar indicators use `value`; composites use named fields.
    value: float | None = None
    fields: dict[str, float | None] = Field(default_factory=dict)
    detail: str | None = None


class IndicatorSeriesResult(BaseModel):
    indicator: IndicatorId
    params: dict[str, Any]
    warmup_required: int
    status: IndicatorStatus
    points: list[IndicatorPoint] = Field(default_factory=list)
    latest: IndicatorLatest


class IndicatorBundle(BaseModel):
    """Full calculation output for one OHLCV series."""

    include_forming: bool
    closed_candles_used: int
    forming_included: bool
    series: dict[str, IndicatorSeriesResult]
    latest: dict[str, IndicatorLatest]


class CandleFrame(BaseModel):
    """Internal lightweight OHLCV frame used by calculators."""

    timestamps: list[datetime]
    open: list[float]
    high: list[float]
    low: list[float]
    close: list[float]
    volume: list[float]
    is_closed: list[bool]

    @property
    def size(self) -> int:
        return len(self.timestamps)
