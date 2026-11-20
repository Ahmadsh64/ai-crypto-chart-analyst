# Phase 5.2.4 — Performance Analytics & Backtesting Metrics Engine

## Architecture

```
Historical Replay → Analysis → Trade Simulation → Execution Costs
                                                      ↓
                                         Performance Analytics Engine
                                                      ↓
                              Metrics · Equity · Drawdown · Groups
                                                      ↓
                                    REST + WebSocket + Frontend
```

Analytics **consumes** `SimulatedTrade` + `CostEngine` results. It does **not** simulate fills, change costs, or invent signals.

Version: `performance-analytics-v1.0.0-balanced`

## Pre-implementation audit (summary)

| Topic | Finding |
|---|---|
| Completed trades | `closed_tp`, `closed_sl`; `closed_expired` only when remaining ≤ `QTY_TOLERANCE` |
| Partial exits | `trade_partially_closed` events; `remaining_quantity` > 0 |
| Quantities | `original_quantity`, `executed_quantity`, `remaining_quantity` |
| Gross / net P&L | `CostEngine.trade_summary` / ledger exit nets |
| Entry fee allocation | Proportional via `allocate_entry_fee` on exits |
| Slippage / spread | Decimal ledger fields |
| Timestamps | UTC replay event / execution timestamps |
| Reset / seek | Rebuild sim + costs from 0…index; analytics rebuilds after |
| Initial equity | **Did not exist** — must be explicit config; never invented |
| Per-trade timeframe | **Not on `SimulatedTrade`** — timeframe grouping unavailable |

## Trade classification

| Analytics class | Source statuses | In Win Rate? |
|---|---|---|
| `closed` | `closed_tp`, `closed_sl`, and `closed_expired` **only when remaining ≤ sim `QTY_TOLERANCE` (1e-9)** (+ flat ambiguous) | Yes |
| `expired` | `closed_expired` with remaining quantity above tolerance | No (cash-flow only if costs exist) |
| `partially_closed` | `partially_closed` | No (cash-flow only) |
| `open` | `open`, `pending_entry` | No |
| `cancelled` | `cancelled` | No |
| `invalidated` | `rejected` | No |
| `ambiguous` | non-flat `ambiguous_execution` | No |

**Win:** completed net P&L > 0 · **Loss:** < 0 · **Break-even:** = 0 (in denominator, not win/loss counts).

## Metric definitions

- **Win Rate** = Winning completed / Completed × 100
- **Profit Factor** = Gross profit (sum positive nets) / |Gross loss|
  - No losses + profit > 0 → `availability=infinite`
  - No completed / zero both sides → `unavailable` (not a fake 0)
- **Net P&L** default for performance (from cost engine)
- **R multiple** = net P&L / (|entry − initial_SL| × original qty) when risk > 0; else unavailable
- **Returns / drawdown %** require configured `initial_equity`

## Equity curves (separate)

1. **Completed-trade** — one point per fully closed trade at exit timestamp (tie-break `trade_id`)
2. **Realized cash-flow** — each exit ledger leg; entry slip/spread deducted once on first exit so cumulative matches trade net

Never mixes unrealized mark-to-market into realized equity.

`Ending equity = initial_equity + cumulative net` when initial equity is set.

## Drawdown

`DD = running peak equity − equity` (≥ 0). Max DD is peak-to-trough max. Recovery only if equity later returns to that peak. Without initial equity → drawdown unavailable.

## Grouping

Symbol, direction, period (UTC daily/weekly/monthly), exit type (`tp`/`sl`/`expired`/`other`).  
**Timeframe:** unavailable (no TF on trade model).

## Initial equity

Optional. If missing: absolute nets still computed; % returns, equity series values, and drawdown marked unavailable. Never assume a balance.

## REST (`/api/v1/replay/sessions/{id}/analytics/…`)

- `POST …/enable` · `POST …/disable`
- `GET …` · `GET …/summary` · `GET …/equity` · `GET …/drawdown` · `GET …/groups` · `GET …/trades`
- `GET/PUT …/config` · `PUT …/filter`

## WebSocket (`/ws/replay`)

`analytics_enabled`, `analytics_disabled`, `analytics_summary_update`, `analytics_equity_update`, `analytics_drawdown_update`, `analytics_group_update`, `analytics_error`

## Caching

Fingerprint: session + event index + analytics config + cost model version + filter + trade/ledger signature. Invalidated on reset, seek rebuild, config/filter change.

## Worked example (labeled fixture)

LONG entry 100×1, exit 110×1, fees/slip/spread = 0, initial equity 1000:

| Metric | Value |
|---|---|
| Gross / Net | 10 |
| Win Rate | 100% |
| Profit Factor | ∞ (`infinite`) |
| R (SL 95) | 2.0 |
| Ending equity | 1010 |
| Max DD | 0 |

Independent hand calc matches `AnalyticsEngine`.

## Known limitations

- Live market windows may yield zero completed trades (analysis `NO TRADE`) — fixtures are labeled, not live proof.
- Timeframe grouping unavailable without inventing metadata.
- Unrealized P&L for open trades is not implemented in this phase (no mark feed wired into analytics).
