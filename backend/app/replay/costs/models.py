"""Execution cost models (Phase 5.2.3)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.exchanges.types import ExchangeId, MarketType
from app.replay.costs.enums import (
    ExecutionRole,
    FeeConfigSource,
    MakerTakerClass,
    OrderTypeEstimate,
)
from app.replay.simulation.enums import TradeDirection


def _dec_ser(v: Decimal | None) -> str | None:
    if v is None:
        return None
    return format(v, "f")


class LedgerEntry(BaseModel):
    execution_id: str
    source_event_id: str
    trade_id: str
    replay_session_id: str
    event_timestamp: datetime
    exchange: ExchangeId
    market_type: MarketType
    symbol: str
    direction: TradeDirection
    execution_role: ExecutionRole
    order_type_estimate: OrderTypeEstimate
    maker_taker: MakerTakerClass
    maker_taker_estimated: bool = True
    executed_quantity: Decimal
    reference_price: Decimal
    execution_price: Decimal
    executed_notional: Decimal
    fee_rate: Decimal
    fee_amount: Decimal
    slippage_amount: Decimal
    spread_cost: Decimal
    gross_realized_pnl: Decimal | None = None
    allocated_entry_fee: Decimal | None = None
    net_realized_pnl: Decimal | None = None
    cost_model_version: str
    fee_config_source: FeeConfigSource
    fee_schedule_version: str
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}

    def public_dict(self) -> dict[str, Any]:
        d = self.model_dump(mode="json")
        for key in (
            "executed_quantity",
            "reference_price",
            "execution_price",
            "executed_notional",
            "fee_rate",
            "fee_amount",
            "slippage_amount",
            "spread_cost",
            "gross_realized_pnl",
            "allocated_entry_fee",
            "net_realized_pnl",
        ):
            if key in d and d[key] is not None:
                d[key] = str(d[key])
        return d


class TradeCostSummary(BaseModel):
    trade_id: str
    session_id: str
    symbol: str
    direction: TradeDirection
    lifecycle_status: str
    total_executed_quantity: Decimal
    remaining_open_quantity: Decimal
    total_gross_realized_pnl: Decimal
    total_entry_fees: Decimal
    total_exit_fees: Decimal
    total_fees: Decimal
    total_slippage: Decimal
    total_spread_cost: Decimal
    total_costs: Decimal
    net_realized_pnl: Decimal
    cost_model_version: str
    fee_config_source: FeeConfigSource
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    ledger_entry_count: int = 0

    model_config = {"arbitrary_types_allowed": True}


class SessionCostSummary(BaseModel):
    session_id: str
    enabled: bool
    cost_model_version: str
    fee_config_source: FeeConfigSource
    fee_schedule_version: str
    gross_realized_pnl: Decimal
    total_entry_fees: Decimal
    total_exit_fees: Decimal
    total_fees: Decimal
    total_slippage: Decimal
    total_spread_cost: Decimal
    total_costs: Decimal
    net_realized_pnl: Decimal
    trade_count: int
    ledger_entry_count: int
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str
    config: dict[str, Any] = Field(default_factory=dict)
    replay_timestamp: datetime | None = None

    model_config = {"arbitrary_types_allowed": True}


class CostSnapshot(BaseModel):
    session_id: str
    enabled: bool
    summary: SessionCostSummary
    trades: list[TradeCostSummary] = Field(default_factory=list)
    recent_ledger: list[LedgerEntry] = Field(default_factory=list)
    cost_model_version: str
    disclaimer: str
