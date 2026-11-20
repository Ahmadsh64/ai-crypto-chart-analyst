"""Simulation validation helpers (Phase 5.2.2)."""

from __future__ import annotations

from app.replay.simulation.config import QTY_TOLERANCE
from app.replay.simulation.models import SimulatedTrade


def quantities_conserved(trade: SimulatedTrade, *, tol: float = QTY_TOLERANCE) -> bool:
    exited = (
        trade.quantity_closed_tp
        + trade.quantity_closed_sl
        + trade.quantity_closed_expired
    )
    total = trade.remaining_quantity + exited
    return abs(total - trade.original_quantity) <= tol


def assert_quantities(trade: SimulatedTrade, *, tol: float = QTY_TOLERANCE) -> None:
    if not quantities_conserved(trade, tol=tol):
        raise AssertionError(
            f"Quantity conservation violated for {trade.trade_id}: "
            f"orig={trade.original_quantity} remaining={trade.remaining_quantity} "
            f"tp={trade.quantity_closed_tp} sl={trade.quantity_closed_sl} "
            f"exp={trade.quantity_closed_expired}"
        )
