"""Scanner configuration (Phase 5.5) — no engine threshold changes."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.scanner.execution_timeframes import EXECUTION_TIMEFRAMES


class ScannerConfig(BaseModel):
    """Operational knobs only — does not alter Decision/Trade Plan formulas."""

    enabled: bool = True
    scan_interval_seconds: float = Field(default=300.0, ge=30.0, le=3600.0)
    max_concurrent_per_exchange: int = Field(default=2, ge=1, le=8)
    max_pairs_per_market: int = Field(default=25, ge=1, le=200)
    min_quote_volume_24h: float = Field(default=500_000.0, ge=0.0)
    ohlcv_cache_ttl_seconds: float = Field(default=90.0, ge=15.0, le=600.0)
    ticker_prefetch: bool = True
    # Manual/API-triggered scans preferred on boot; scheduler still starts idle loop.
    auto_start: bool = True
    default_exchanges: list[ExchangeId] = Field(
        default_factory=lambda: [ExchangeId.BINANCE, ExchangeId.BYBIT],
    )
    default_market_types: list[MarketType] = Field(
        default_factory=lambda: [
            MarketType.SPOT,
            MarketType.USDT_M_FUTURES,
            MarketType.LINEAR_PERPETUAL,
        ],
    )
    # Independent execution-TF matrix (Option A). Analysis always loads full MTF ladder.
    execution_timeframes: list[Timeframe] = Field(
        default_factory=lambda: list(EXECUTION_TIMEFRAMES),
    )
    approaching_entry_pct: float = Field(
        default=0.5,
        ge=0.05,
        le=5.0,
        description="Within this % of entry zone edge → APPROACHING_ENTRY",
    )


DEFAULT_SCANNER_CONFIG = ScannerConfig()
