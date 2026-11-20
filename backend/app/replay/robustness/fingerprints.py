"""Deterministic fingerprints for prefix / seek / perturbation comparisons."""

from __future__ import annotations

import json
from typing import Any

from app.replay.analysis.models import HistoricalAnalysisSnapshot
from app.replay.analytics.models import AnalyticsSnapshot
from app.replay.costs.models import CostSnapshot
from app.replay.simulation.models import SimulationSnapshot


def _stable(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))


def analysis_fingerprint(snap: HistoricalAnalysisSnapshot) -> str:
    """Normalize analysis fields that must be prefix-invariant at clock T."""
    indicators = {}
    for tf, bundle in (snap.indicators or {}).items():
        if bundle is None:
            continue
        indicators[tf] = {
            "values": bundle.values,
            "closed_candles_used": bundle.closed_candles_used,
            "warming_up": bundle.warming_up,
        }
    structure = {
        tf: s.model_dump(mode="json") for tf, s in (snap.structure or {}).items()
    }
    liquidity = {
        tf: s.model_dump(mode="json") for tf, s in (snap.liquidity or {}).items()
    }
    ob_fvg = {tf: s.model_dump(mode="json") for tf, s in (snap.ob_fvg or {}).items()}
    payload = {
        "decision": snap.decision,
        "decision_reason": snap.decision_reason,
        "lifecycle_status": snap.lifecycle_status,
        "direction": snap.direction,
        "bullish_score": snap.bullish_score,
        "bearish_score": snap.bearish_score,
        "confluence_strength": snap.confluence_strength,
        "conflicts": list(snap.conflicts or []),
        "stop_loss": snap.stop_loss,
        "take_profit_levels": list(snap.take_profit_levels or []),
        "risk_reward": snap.risk_reward,
        "entry_zone": snap.entry_zone,
        "closed_candle_counts": snap.closed_candle_counts,
        "structure": structure,
        "liquidity": liquidity,
        "ob_fvg": ob_fvg,
        "indicators": indicators,
        "trade_plan_status": snap.trade_plan_status,
        "data_quality": snap.data_quality,
        "data_ready": snap.data_ready,
    }
    return _stable(payload)


def simulation_fingerprint(snap: SimulationSnapshot) -> str:
    trades = []
    for t in sorted(snap.trades, key=lambda x: x.trade_id):
        trades.append(
            {
                "trade_id": t.trade_id,
                "lifecycle_status": t.lifecycle_status,
                "direction": t.direction,
                "entry_price": t.entry_price,
                "original_quantity": t.original_quantity,
                "remaining_quantity": t.remaining_quantity,
                "executed_quantity": t.executed_quantity,
                "quantity_closed_tp": t.quantity_closed_tp,
                "quantity_closed_sl": t.quantity_closed_sl,
                "quantity_closed_expired": t.quantity_closed_expired,
                "execution_events": [
                    {
                        "event_type": e.event_type,
                        "price": e.price,
                        "quantity": e.quantity,
                        "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                        "reason": e.reason,
                    }
                    for e in sorted(
                        t.execution_events,
                        key=lambda e: (e.timestamp.isoformat(), e.event_id),
                    )
                ],
            }
        )
    ov = snap.overview
    payload = {
        "open_count": ov.open_count,
        "closed_count": ov.closed_count,
        "pending_count": ov.pending_count,
        "partially_closed_count": ov.partially_closed_count,
        "total_trades": ov.total_trades,
        "trades": trades,
    }
    return _stable(payload)


def cost_fingerprint(snap: CostSnapshot) -> str:
    summary = snap.summary
    payload = {
        "ledger_entry_count": summary.ledger_entry_count,
        "total_fees": str(summary.total_fees),
        "total_slippage": str(summary.total_slippage),
        "total_spread_cost": str(summary.total_spread_cost),
        "total_costs": str(summary.total_costs),
        "net_realized_pnl": str(summary.net_realized_pnl),
        "gross_realized_pnl": str(summary.gross_realized_pnl),
        "entries": [
            {
                "execution_id": e.execution_id,
                "trade_id": e.trade_id,
                "role": e.execution_role,
                "quantity": str(e.executed_quantity),
                "fee": str(e.fee_amount),
                "slippage": str(e.slippage_amount),
                "spread": str(e.spread_cost),
                "timestamp": e.event_timestamp.isoformat(),
            }
            for e in sorted(snap.recent_ledger, key=lambda x: x.execution_id)
        ],
    }
    return _stable(payload)


def analytics_fingerprint(snap: AnalyticsSnapshot) -> str:
    s = snap.summary
    pf = s.profitability.profit_factor
    wr = s.trade_stats.win_rate
    payload = {
        "completed_trades": s.trade_stats.completed_trades,
        "total_simulated_trades": s.trade_stats.total_simulated_trades,
        "included_completed_trades": s.included_completed_trades,
        "net_realized_pnl": str(s.profitability.total_net_realized_pnl),
        "profit_factor_value": str(pf.value) if pf.value is not None else None,
        "profit_factor_availability": pf.availability,
        "win_rate_value": str(wr.value) if wr.value is not None else None,
        "win_rate_availability": wr.availability,
        "max_drawdown": str(snap.drawdown.max_drawdown),
        "equity_completed_points": len(snap.equity_completed.points),
        "equity_cashflow_points": len(snap.equity_cashflow.points),
        "drawdown_points": len(snap.drawdown.series),
        "completed_trade_ids": sorted(t.trade_id for t in snap.completed_trades),
    }
    return _stable(payload)
