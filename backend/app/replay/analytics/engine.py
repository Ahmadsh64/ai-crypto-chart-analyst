"""Performance analytics engine — consumes simulation + cost results (Phase 5.2.4)."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from app.replay.analytics.config import (
    ANALYTICS_VERSION,
    AnalyticsConfig,
    default_analytics_config,
)
from app.replay.analytics.drawdown import compute_drawdown
from app.replay.analytics.equity_curve import (
    build_cashflow_curve_from_ledger,
    build_completed_trade_curve,
    empty_curve,
)
from app.replay.analytics.metrics_calculator import (
    compute_profitability,
    compute_returns,
    compute_trade_statistics,
)
from app.replay.analytics.models import (
    AnalyticsSnapshot,
    AnalyticsTradeRow,
    PerformanceSummary,
)
from app.replay.analytics.performance_groups import build_groups
from app.replay.analytics.risk_metrics import compute_risk_reward, planned_risk_amount
from app.replay.analytics.trade_filter import AnalyticsFilter, classify_trade
from app.replay.analytics.validation import (
    reconcile_drawdown,
    reconcile_equity,
    reconcile_groups,
    reconcile_summary,
)
from app.replay.costs.engine import CostEngine
from app.replay.simulation.models import SimulatedTrade

logger = logging.getLogger(__name__)


class AnalyticsEngine:
    """Isolated analytics layer. Does not simulate trades or alter costs."""

    def __init__(
        self,
        *,
        session_id: str,
        config: AnalyticsConfig | None = None,
    ) -> None:
        self.session_id = session_id
        self.config = config or default_analytics_config()
        self.enabled = False
        self._cache_key: str | None = None
        self._cached_snapshot: AnalyticsSnapshot | None = None
        self._last_source_fingerprint: str | None = None

    def reset(self) -> None:
        self._cache_key = None
        self._cached_snapshot = None
        self._last_source_fingerprint = None

    def enable(self) -> None:
        self.enabled = True
        self.config.enabled = True
        self.reset()

    def disable(self) -> None:
        self.enabled = False
        self.config.enabled = False
        self.reset()

    def update_config(self, config: AnalyticsConfig) -> None:
        was = self.enabled
        self.config = config
        self.config.enabled = was
        self.enabled = was
        self.reset()

    def _fingerprint(
        self,
        trades: list[SimulatedTrade],
        cost_engine: CostEngine,
        *,
        event_index: int | None,
        filt: AnalyticsFilter,
    ) -> str:
        ledger_n = len(cost_engine.ledger)
        trade_sig = ",".join(
            f"{t.trade_id}:{t.lifecycle_status}:{len(t.execution_events)}"
            for t in sorted(trades, key=lambda x: x.trade_id)
        )
        return "|".join(
            [
                self.session_id,
                str(event_index),
                self.config.config_version,
                format(self.config.initial_equity, "f")
                if self.config.initial_equity is not None
                else "none",
                cost_engine.config.config_version,
                str(cost_engine.enabled),
                str(ledger_n),
                filt.cache_key(),
                trade_sig,
            ]
        )

    def compute(
        self,
        trades: list[SimulatedTrade],
        cost_engine: CostEngine,
        *,
        replay_timestamp: datetime | None = None,
        event_index: int | None = None,
        filt: AnalyticsFilter | None = None,
    ) -> AnalyticsSnapshot:
        filt = filt or AnalyticsFilter()
        fp = self._fingerprint(
            trades, cost_engine, event_index=event_index, filt=filt
        )
        if (
            self._cached_snapshot is not None
            and self._last_source_fingerprint == fp
            and self.enabled
        ):
            return self._cached_snapshot

        snap = self._compute_uncached(
            trades,
            cost_engine,
            replay_timestamp=replay_timestamp,
            event_index=event_index,
            filt=filt,
        )
        if self.enabled:
            self._cached_snapshot = snap
            self._last_source_fingerprint = fp
        return snap

    def _compute_uncached(
        self,
        trades: list[SimulatedTrade],
        cost_engine: CostEngine,
        *,
        replay_timestamp: datetime | None,
        event_index: int | None,
        filt: AnalyticsFilter,
    ) -> AnalyticsSnapshot:
        cfg = self.config
        assumptions: list[str] = [
            "Performance metrics use NET realized P&L from the execution cost engine.",
            "Completed-trade statistics exclude open and partially closed trades.",
        ]
        warnings: list[str] = []

        cost_by_id = {}
        if cost_engine.enabled:
            for t in trades:
                if cost_engine.ledger.for_trade(t.trade_id):
                    cost_by_id[t.trade_id] = cost_engine.trade_summary(t)
        else:
            warnings.append(
                "Cost engine disabled — analytics require cost results for P&L metrics."
            )

        classified = [
            classify_trade(
                t,
                cost_by_id.get(t.trade_id),
                include_ambiguous_as_closed_when_flat=cfg.include_ambiguous_as_closed_when_flat,
            )
            for t in trades
        ]
        classified = [c for c in classified if filt.matches(c)]

        completed = [c for c in classified if c.is_completed and c.cost is not None]
        partials = [c for c in classified if c.analytics_class == "partially_closed"]
        opens = [c for c in classified if c.analytics_class == "open"]

        trade_stats = compute_trade_statistics(classified)
        profitability = compute_profitability(completed)
        risk_reward = compute_risk_reward(completed)
        returns = compute_returns(
            initial_equity=cfg.initial_equity,
            cumulative_net=profitability.total_net_realized_pnl,
            completed_nets=[c.cost.net_realized_pnl for c in completed if c.cost],
        )

        completed_ids = {c.trade.trade_id for c in completed}
        equity_completed = build_completed_trade_curve(
            completed, initial_equity=cfg.initial_equity
        )
        equity_cashflow = build_cashflow_curve_from_ledger(
            cost_engine.ledger.all_entries() if cost_engine.enabled else [],
            initial_equity=cfg.initial_equity,
            include_partial=cfg.include_partial_realized_in_cashflow,
            completed_ids=completed_ids,
        )

        # Drawdown uses the configured equity curve mode
        primary = (
            equity_completed
            if cfg.equity_curve_mode == "completed_trade"
            else equity_cashflow
        )
        if cfg.initial_equity is None:
            dd = compute_drawdown(
                empty_curve(primary.mode, None, "initial_equity_not_configured")
            )
        else:
            dd = compute_drawdown(primary)

        groups = build_groups(classified, cfg)

        # Carry cost-model assumptions
        if cost_engine.enabled and cost_by_id:
            sample = next(iter(cost_by_id.values()))
            assumptions.extend(sample.assumptions[:4])
            warnings.extend(sample.warnings[:4])

        equity_source = (
            "configured"
            if cfg.initial_equity is not None
            else "not_configured"
        )

        summary = PerformanceSummary(
            session_id=self.session_id,
            enabled=self.enabled,
            analytics_version=cfg.config_version or ANALYTICS_VERSION,
            cost_model_version=(
                cost_engine.config.config_version if cost_engine.enabled else None
            ),
            replay_timestamp=replay_timestamp,
            event_index=event_index,
            quote_currency=cfg.quote_currency,
            initial_equity=cfg.initial_equity,
            initial_equity_source=equity_source,
            trade_stats=trade_stats,
            profitability=profitability,
            risk_reward=risk_reward,
            returns=returns,
            drawdown=dd,
            included_completed_trades=len(completed),
            excluded_open_trades=len(opens),
            excluded_partial_trades=len(partials),
            assumptions=list(dict.fromkeys(assumptions)),
            warnings=[],
            disclaimer=cfg.disclaimer,
            filter_context={
                "exchange": filt.exchange,
                "symbol": filt.symbol,
                "market_type": filt.market_type,
                "direction": filt.direction,
                "exit_type": filt.exit_type,
                "start_time": filt.start_time_iso,
                "end_time": filt.end_time_iso,
            },
            config=cfg.snapshot(),
        )

        summary.warnings.extend(reconcile_summary(summary))
        summary.warnings.extend(
            reconcile_equity(
                equity_completed,
                initial_equity=cfg.initial_equity,
                cumulative_net=profitability.total_net_realized_pnl,
            )
        )
        summary.warnings.extend(reconcile_drawdown(dd))
        summary.warnings.extend(
            reconcile_groups(groups, profitability.total_net_realized_pnl)
        )
        summary.warnings.extend(warnings)
        summary.warnings = list(dict.fromkeys(summary.warnings))

        rows: list[AnalyticsTradeRow] = []
        for c in completed:
            r_mult = None
            risk = planned_risk_amount(c)
            if risk and c.cost:
                r_mult = (c.cost.net_realized_pnl / risk).quantize(Decimal("0.00000001"))
            rows.append(
                AnalyticsTradeRow(
                    trade_id=c.trade.trade_id,
                    symbol=c.trade.symbol,
                    direction=c.trade.direction,
                    lifecycle_status=c.trade.lifecycle_status,
                    analytics_class=c.analytics_class,
                    exit_type=c.exit_type,
                    net_realized_pnl=c.cost.net_realized_pnl if c.cost else None,
                    gross_realized_pnl=(
                        c.cost.total_gross_realized_pnl if c.cost else None
                    ),
                    r_multiple=r_mult,
                    entry_timestamp=c.trade.entry_timestamp,
                    exit_timestamp=c.trade.exit_timestamp,
                    included_in_completed_stats=True,
                )
            )

        return AnalyticsSnapshot(
            session_id=self.session_id,
            enabled=self.enabled,
            analytics_version=cfg.config_version or ANALYTICS_VERSION,
            summary=summary,
            equity_completed=equity_completed,
            equity_cashflow=equity_cashflow,
            drawdown=dd,
            groups=groups,
            completed_trades=rows,
            disclaimer=cfg.disclaimer,
        )

    def snapshot(
        self,
        trades: list[SimulatedTrade],
        cost_engine: CostEngine,
        *,
        replay_timestamp: datetime | None = None,
        event_index: int | None = None,
        filt: AnalyticsFilter | None = None,
    ) -> AnalyticsSnapshot:
        return self.compute(
            trades,
            cost_engine,
            replay_timestamp=replay_timestamp,
            event_index=event_index,
            filt=filt,
        )
