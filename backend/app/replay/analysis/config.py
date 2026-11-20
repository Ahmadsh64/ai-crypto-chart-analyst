"""Historical analysis pipeline configuration (Phase 5.2.1)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.analysis.indicators.models import DEFAULT_INDICATORS, IndicatorId
from app.exchanges.types import Timeframe
from app.replay.config import REPLAY_TIMEFRAMES

STRATEGY_CONFIG_VERSION = "historical-analysis-v1.0.0"

# Keep ladder aligned with Phase 4.1 / 5.1.
HISTORICAL_TIMEFRAMES: tuple[Timeframe, ...] = REPLAY_TIMEFRAMES

# Compact indicator set for replay snapshots (subset of Phase 3.1 defaults).
HISTORICAL_INDICATORS: tuple[IndicatorId, ...] = tuple(
    ind
    for ind in DEFAULT_INDICATORS
    if ind
    in {
        IndicatorId.EMA_20,
        IndicatorId.EMA_50,
        IndicatorId.EMA_200,
        IndicatorId.RSI_14,
        IndicatorId.MACD,
        IndicatorId.STOCH_RSI,
        IndicatorId.ATR_14,
        IndicatorId.BOLLINGER,
        IndicatorId.VOLUME_SMA_20,
        IndicatorId.RELATIVE_VOLUME,
    }
)


class HistoricalAnalysisConfig(BaseModel):
    config_version: str = STRATEGY_CONFIG_VERSION
    timeframes: tuple[Timeframe, ...] = HISTORICAL_TIMEFRAMES
    indicators: tuple[IndicatorId, ...] = HISTORICAL_INDICATORS
    """Max stored snapshots per session (oldest dropped when exceeded)."""
    max_history: int = Field(default=5000, ge=10, le=50_000)
    """Cache analysis by event index while clock/config unchanged."""
    enable_cache: bool = True

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


DEFAULT_HISTORICAL_ANALYSIS_CONFIG = HistoricalAnalysisConfig()
