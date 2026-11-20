"""Trade classification and filtering for analytics (Phase 5.2.4)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.replay.analytics.enums import AnalyticsTradeClass, ExitTypeGroup
from app.replay.costs.models import TradeCostSummary
from app.replay.simulation.config import QTY_TOLERANCE
from app.replay.simulation.models import SimulatedTrade

# Terminal closed statuses that are always completed when the simulator sets them
# after flattening the position (TP/SL paths already require remaining ≤ tolerance).
_CLOSED_FLAT = frozenset({"closed_tp", "closed_sl"})
_PARTIAL = frozenset({"partially_closed"})
_OPEN = frozenset({"open", "pending_entry"})
_CANCELLED = frozenset({"cancelled", "rejected"})
_EPS = Decimal("1e-12")
# Same flatness threshold the simulation engine uses when closing TP/SL positions.
_QTY_TOL = Decimal(str(QTY_TOLERANCE))


@dataclass(frozen=True)
class ClassifiedTrade:
    trade: SimulatedTrade
    cost: TradeCostSummary | None
    analytics_class: AnalyticsTradeClass
    exit_type: ExitTypeGroup
    is_completed: bool
    """True when included in completed-trade Win Rate / PF denominator."""
    has_realized_pnl: bool


def map_exit_type(lifecycle: str) -> ExitTypeGroup:
    if lifecycle == "closed_tp":
        return "tp"
    if lifecycle == "closed_sl":
        return "sl"
    if lifecycle == "closed_expired":
        return "expired"
    if lifecycle in _PARTIAL:
        return "other"
    if lifecycle == "ambiguous_execution":
        return "other"
    return "unknown"


def _parse_qty(value: object) -> Decimal | None:
    """Return a finite Decimal quantity, or None when flatness cannot be proven."""
    if value is None:
        return None
    try:
        qty = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not qty.is_finite():
        return None
    return qty


def _position_is_flat(remaining: Decimal | None) -> bool:
    """True only when remaining quantity is known and ≤ simulation tolerance."""
    if remaining is None:
        return False
    return remaining <= _QTY_TOL


def _has_realized_cost(cost: TradeCostSummary | None) -> bool:
    return cost is not None and (
        cost.net_realized_pnl != 0 or cost.ledger_entry_count > 0
    )


def classify_trade(
    trade: SimulatedTrade,
    cost: TradeCostSummary | None,
    *,
    include_ambiguous_as_closed_when_flat: bool = True,
) -> ClassifiedTrade:
    status = trade.lifecycle_status
    remaining = _parse_qty(trade.remaining_quantity)
    executed = _parse_qty(trade.executed_quantity) or Decimal("0")
    exit_type = map_exit_type(status)

    # closed_expired is a documented terminal closed state, but only when the
    # position is actually flat. Remaining qty above sim tolerance must not
    # enter completed-trade statistics (Win Rate / PF / avg net / completed equity).
    if status == "closed_expired":
        if _position_is_flat(remaining):
            return ClassifiedTrade(
                trade=trade,
                cost=cost,
                analytics_class="closed",
                exit_type=exit_type,
                is_completed=True,
                has_realized_pnl=cost is not None,
            )
        return ClassifiedTrade(
            trade=trade,
            cost=cost,
            analytics_class="expired",
            exit_type=exit_type,
            is_completed=False,
            has_realized_pnl=_has_realized_cost(cost),
        )

    if status in _CLOSED_FLAT:
        return ClassifiedTrade(
            trade=trade,
            cost=cost,
            analytics_class="closed",
            exit_type=exit_type,
            is_completed=True,
            has_realized_pnl=cost is not None,
        )

    if status in _PARTIAL:
        return ClassifiedTrade(
            trade=trade,
            cost=cost,
            analytics_class="partially_closed",
            exit_type=exit_type,
            is_completed=False,
            has_realized_pnl=cost is not None and (cost.net_realized_pnl != 0 or cost.ledger_entry_count > 0),
        )

    if status == "ambiguous_execution":
        flat = remaining <= _EPS and executed > 0
        if include_ambiguous_as_closed_when_flat and flat:
            return ClassifiedTrade(
                trade=trade,
                cost=cost,
                analytics_class="closed",
                exit_type="other",
                is_completed=True,
                has_realized_pnl=cost is not None,
            )
        return ClassifiedTrade(
            trade=trade,
            cost=cost,
            analytics_class="ambiguous",
            exit_type="other",
            is_completed=False,
            has_realized_pnl=False,
        )

    if status in _OPEN:
        return ClassifiedTrade(
            trade=trade,
            cost=cost,
            analytics_class="open",
            exit_type="unknown",
            is_completed=False,
            has_realized_pnl=False,
        )

    if status == "cancelled":
        return ClassifiedTrade(
            trade=trade,
            cost=cost,
            analytics_class="cancelled",
            exit_type="unknown",
            is_completed=False,
            has_realized_pnl=False,
        )

    if status == "rejected":
        return ClassifiedTrade(
            trade=trade,
            cost=cost,
            analytics_class="invalidated",
            exit_type="unknown",
            is_completed=False,
            has_realized_pnl=False,
        )

    return ClassifiedTrade(
        trade=trade,
        cost=cost,
        analytics_class="invalidated",
        exit_type="unknown",
        is_completed=False,
        has_realized_pnl=False,
    )


@dataclass
class AnalyticsFilter:
    exchange: str | None = None
    symbol: str | None = None
    market_type: str | None = None
    direction: str | None = None
    exit_type: str | None = None
    # Date range on trade exit / decision timestamps (UTC)
    start_time_iso: str | None = None
    end_time_iso: str | None = None

    def matches(self, item: ClassifiedTrade) -> bool:
        t = item.trade
        if self.exchange and t.exchange.value != self.exchange:
            return False
        if self.symbol and t.symbol.upper() != self.symbol.upper():
            return False
        if self.market_type and t.market_type.value != self.market_type:
            return False
        if self.direction and t.direction != self.direction:
            return False
        if self.exit_type and item.exit_type != self.exit_type:
            return False
        ts = t.exit_timestamp or t.entry_timestamp or t.decision_timestamp
        if self.start_time_iso and ts is not None:
            if ts.isoformat() < self.start_time_iso:
                return False
        if self.end_time_iso and ts is not None:
            if ts.isoformat() > self.end_time_iso:
                return False
        return True

    def cache_key(self) -> str:
        return "|".join(
            [
                self.exchange or "*",
                self.symbol or "*",
                self.market_type or "*",
                self.direction or "*",
                self.exit_type or "*",
                self.start_time_iso or "*",
                self.end_time_iso or "*",
            ]
        )
