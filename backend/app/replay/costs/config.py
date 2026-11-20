"""Execution cost configuration (Phase 5.2.3).

Fee rates are SIMULATION ASSUMPTIONS unless the user or environment supplies them.
They are NOT verified live exchange fee schedules.
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.exchanges.types import ExchangeId, MarketType
from app.replay.costs.enums import (
    FeeConfigSource,
    MakerTakerFallback,
    SlippagePolicy,
    SpreadPolicy,
)

COST_MODEL_VERSION = "execution-costs-v1.0.0-balanced"

# Documented EXAMPLE defaults only — not live exchange quotes.
EXAMPLE_FEE_SCHEDULES: dict[tuple[str, str], tuple[str, str]] = {
    # (exchange, market_type) -> (maker, taker) as decimal strings
    ("binance", "spot"): ("0.001", "0.001"),
    ("binance", "usdt_m_futures"): ("0.0002", "0.0004"),
    ("bybit", "spot"): ("0.001", "0.001"),
    ("bybit", "linear_perpetual"): ("0.0002", "0.00055"),
}


def _d(value: str | float | Decimal) -> Decimal:
    return Decimal(str(value))


class FeeSchedule(BaseModel):
    exchange: ExchangeId
    market_type: MarketType
    maker_fee_rate: Decimal
    taker_fee_rate: Decimal
    fee_currency: str = "quote"
    schedule_version: str = "example-v1"
    source: FeeConfigSource = "example_default"

    model_config = {"arbitrary_types_allowed": True}

    @field_validator("maker_fee_rate", "taker_fee_rate", mode="before")
    @classmethod
    def coerce_decimal(cls, v: Any) -> Decimal:
        d = _d(v)
        if d < 0:
            raise ValueError("Fee rates must be non-negative")
        if d > 1:
            raise ValueError("Fee rates must be <= 1.0 (100%)")
        return d


class ExecutionCostConfig(BaseModel):
    config_version: str = COST_MODEL_VERSION
    enabled: bool = False

    # Global overrides (apply to all venues when set)
    maker_fee_rate: Decimal | None = None
    taker_fee_rate: Decimal | None = None
    fee_currency: str = "quote"
    fee_source: FeeConfigSource = "example_default"
    fee_schedule_version: str = "example-v1"

    slippage_policy: SlippagePolicy = "fixed_bps"
    slippage_bps: Decimal = Field(default=Decimal("1"))  # 1 bps
    slippage_percentage: Decimal = Field(default=Decimal("0.0001"))  # 0.01%

    spread_policy: SpreadPolicy = "none"
    spread_bps: Decimal = Field(default=Decimal("2"))
    spread_percentage: Decimal = Field(default=Decimal("0.0002"))

    maker_taker_fallback: MakerTakerFallback = "assume_taker"
    contract_multiplier: Decimal = Field(default=Decimal("1"))

    disclaimer: str = (
        "HISTORICAL SIMULATION — NOT REAL EXECUTION — COSTS ARE ESTIMATED. "
        "Fee rates are user/environment/example assumptions, not verified live exchange fees."
    )

    model_config = {"arbitrary_types_allowed": True}

    @field_validator(
        "maker_fee_rate",
        "taker_fee_rate",
        "slippage_bps",
        "slippage_percentage",
        "spread_bps",
        "spread_percentage",
        "contract_multiplier",
        mode="before",
    )
    @classmethod
    def coerce_optional_decimal(cls, v: Any) -> Any:
        if v is None or v == "":
            return None
        return _d(v)

    @model_validator(mode="after")
    def validate_rates(self) -> ExecutionCostConfig:
        for name in ("maker_fee_rate", "taker_fee_rate"):
            val = getattr(self, name)
            if val is not None and val < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.contract_multiplier <= 0:
            raise ValueError("contract_multiplier must be > 0")
        if self.slippage_bps < 0 or self.spread_bps < 0:
            raise ValueError("bps values must be non-negative")
        if self.slippage_percentage < 0 or self.spread_percentage < 0:
            raise ValueError("percentage values must be non-negative")
        return self

    def resolve_fee_schedule(
        self,
        exchange: ExchangeId,
        market_type: MarketType,
    ) -> FeeSchedule:
        """Resolve maker/taker rates with source attribution."""
        if self.maker_fee_rate is not None and self.taker_fee_rate is not None:
            return FeeSchedule(
                exchange=exchange,
                market_type=market_type,
                maker_fee_rate=self.maker_fee_rate,
                taker_fee_rate=self.taker_fee_rate,
                fee_currency=self.fee_currency,
                schedule_version=self.fee_schedule_version,
                source=self.fee_source,
            )

        env_maker = os.getenv("EXECUTION_COST_MAKER_FEE")
        env_taker = os.getenv("EXECUTION_COST_TAKER_FEE")
        if env_maker is not None and env_taker is not None:
            return FeeSchedule(
                exchange=exchange,
                market_type=market_type,
                maker_fee_rate=_d(env_maker),
                taker_fee_rate=_d(env_taker),
                fee_currency=self.fee_currency,
                schedule_version=os.getenv(
                    "EXECUTION_COST_FEE_SCHEDULE_VERSION", "env-v1"
                ),
                source="environment",
            )

        key = (exchange.value, market_type.value)
        maker_s, taker_s = EXAMPLE_FEE_SCHEDULES.get(key, ("0.001", "0.001"))
        return FeeSchedule(
            exchange=exchange,
            market_type=market_type,
            maker_fee_rate=_d(maker_s),
            taker_fee_rate=_d(taker_s),
            fee_currency=self.fee_currency,
            schedule_version="example-v1",
            source="example_default",
        )

    def snapshot(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        # Ensure decimal-friendly JSON
        for k, v in list(data.items()):
            if isinstance(v, Decimal):
                data[k] = str(v)
        return data


def default_cost_config() -> ExecutionCostConfig:
    return ExecutionCostConfig()


DEFAULT_COST_CONFIG = ExecutionCostConfig()
