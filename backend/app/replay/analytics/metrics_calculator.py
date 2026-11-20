"""Core performance metric calculations (Phase 5.2.4)."""

from __future__ import annotations

from decimal import Decimal
from statistics import median

from app.replay.analytics.models import (
    MetricValue,
    ProfitabilityMetrics,
    ReturnMetrics,
    TradeStatistics,
)
from app.replay.analytics.trade_filter import ClassifiedTrade

ZERO = Decimal("0")


def _q(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.00000001"))


def unavailable(label: str | None = None) -> MetricValue:
    return MetricValue(value=None, availability="unavailable", label=label)


def available(value: Decimal, label: str | None = None) -> MetricValue:
    return MetricValue(value=_q(value), availability="available", label=label)


def infinite(label: str | None = None) -> MetricValue:
    return MetricValue(value=None, availability="infinite", label=label or "undefined_no_losses")


def compute_trade_statistics(items: list[ClassifiedTrade]) -> TradeStatistics:
    completed = [i for i in items if i.is_completed and i.cost is not None]
    wins: list[Decimal] = []
    losses: list[Decimal] = []
    be = 0
    for i in completed:
        assert i.cost is not None
        net = i.cost.net_realized_pnl
        if net > 0:
            wins.append(net)
        elif net < 0:
            losses.append(net)
        else:
            be += 1

    n = len(completed)
    stats = TradeStatistics(
        total_simulated_trades=len(items),
        completed_trades=n,
        open_trades=sum(1 for i in items if i.analytics_class == "open"),
        partially_closed_trades=sum(
            1 for i in items if i.analytics_class == "partially_closed"
        ),
        winning_trades=len(wins),
        losing_trades=len(losses),
        break_even_trades=be,
    )
    if n == 0:
        stats.win_rate = unavailable("no_completed_trades")
        stats.loss_rate = unavailable("no_completed_trades")
    else:
        stats.win_rate = available(Decimal(len(wins)) / Decimal(n) * Decimal("100"))
        stats.loss_rate = available(Decimal(len(losses)) / Decimal(n) * Decimal("100"))

    if wins:
        stats.average_winning_trade = available(sum(wins) / Decimal(len(wins)))
        stats.largest_winning_trade = available(max(wins))
    else:
        stats.average_winning_trade = unavailable("no_winning_trades")
        stats.largest_winning_trade = unavailable("no_winning_trades")

    if losses:
        stats.average_losing_trade = available(sum(losses) / Decimal(len(losses)))
        stats.largest_losing_trade = available(min(losses))  # most negative
    else:
        stats.average_losing_trade = unavailable("no_losing_trades")
        stats.largest_losing_trade = unavailable("no_losing_trades")

    return stats


def compute_profitability(completed: list[ClassifiedTrade]) -> ProfitabilityMetrics:
    mets = ProfitabilityMetrics()
    if not completed:
        mets.profit_factor = unavailable("no_completed_trades")
        mets.average_net_pnl_per_completed = unavailable("no_completed_trades")
        return mets

    nets: list[Decimal] = []
    for i in completed:
        assert i.cost is not None
        c = i.cost
        mets.total_gross_realized_pnl += c.total_gross_realized_pnl
        mets.total_net_realized_pnl += c.net_realized_pnl
        mets.total_trading_fees += c.total_fees
        mets.total_slippage += c.total_slippage
        mets.total_spread_costs += c.total_spread_cost
        mets.total_execution_costs += c.total_costs
        nets.append(c.net_realized_pnl)
        if c.net_realized_pnl > 0:
            mets.gross_profit += c.net_realized_pnl
        elif c.net_realized_pnl < 0:
            mets.gross_loss += c.net_realized_pnl  # negative

    mets.total_gross_realized_pnl = _q(mets.total_gross_realized_pnl)
    mets.total_net_realized_pnl = _q(mets.total_net_realized_pnl)
    mets.total_trading_fees = _q(mets.total_trading_fees)
    mets.total_slippage = _q(mets.total_slippage)
    mets.total_spread_costs = _q(mets.total_spread_costs)
    mets.total_execution_costs = _q(mets.total_execution_costs)
    mets.gross_profit = _q(mets.gross_profit)
    mets.gross_loss = _q(mets.gross_loss)

    n = Decimal(len(completed))
    mets.average_net_pnl_per_completed = available(mets.total_net_realized_pnl / n)
    mets.profit_factor = compute_profit_factor(mets.gross_profit, mets.gross_loss)
    return mets


def compute_profit_factor(gross_profit: Decimal, gross_loss: Decimal) -> MetricValue:
    """PF = sum(positive net) / abs(sum(negative net))."""
    abs_loss = abs(gross_loss)
    if gross_profit == 0 and abs_loss == 0:
        return unavailable("zero_profit_and_loss")
    if abs_loss == 0:
        if gross_profit > 0:
            return infinite("no_losing_trades")
        return unavailable("no_losing_trades_zero_profit")
    return available(gross_profit / abs_loss)


def compute_returns(
    *,
    initial_equity: Decimal | None,
    cumulative_net: Decimal,
    completed_nets: list[Decimal],
) -> ReturnMetrics:
    ret = ReturnMetrics(initial_equity=initial_equity)
    if initial_equity is None:
        ret.current_equity = unavailable("initial_equity_not_configured")
        ret.ending_equity = unavailable("initial_equity_not_configured")
        ret.total_return_pct = unavailable("initial_equity_not_configured")
        ret.average_trade_return_pct = unavailable("initial_equity_not_configured")
        ret.best_trade_return_pct = unavailable("initial_equity_not_configured")
        ret.worst_trade_return_pct = unavailable("initial_equity_not_configured")
        return ret

    ending = _q(initial_equity + cumulative_net)
    ret.current_equity = available(ending)
    ret.ending_equity = available(ending)
    if initial_equity > 0:
        ret.total_return_pct = available(
            cumulative_net / initial_equity * Decimal("100")
        )
        if completed_nets:
            pcts = [n / initial_equity * Decimal("100") for n in completed_nets]
            ret.average_trade_return_pct = available(sum(pcts) / Decimal(len(pcts)))
            ret.best_trade_return_pct = available(max(pcts))
            ret.worst_trade_return_pct = available(min(pcts))
        else:
            ret.average_trade_return_pct = unavailable("no_completed_trades")
            ret.best_trade_return_pct = unavailable("no_completed_trades")
            ret.worst_trade_return_pct = unavailable("no_completed_trades")
    else:
        # Zero initial equity — absolute equity still defined; % returns unavailable.
        ret.total_return_pct = unavailable("initial_equity_zero")
        ret.average_trade_return_pct = unavailable("initial_equity_zero")
        ret.best_trade_return_pct = unavailable("initial_equity_zero")
        ret.worst_trade_return_pct = unavailable("initial_equity_zero")
    return ret


def median_decimal(values: list[Decimal]) -> Decimal:
    if not values:
        return ZERO
    return Decimal(str(median(values)))
