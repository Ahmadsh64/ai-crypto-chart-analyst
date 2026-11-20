# Phase 5.2.2 — Historical Trade Simulation Engine

Simulation-only subsystem that consumes immutable Phase 5.2.1 analysis snapshots and subsequent replay candles to model hypothetical entries, stop losses, take profits, partial exits, and trade lifecycle.

**HISTORICAL SIMULATION — NOT REAL ORDERS.** Fills are hypothetical and do not represent guaranteed real-world execution. No exchange orders, fees, slippage beyond conservative gap rules, or P&L in this phase.

## Architecture

Location: `backend/app/replay/simulation/`

| Module | Role |
|--------|------|
| `config.py` | Entry policy, ambiguity policy, TP allocations, disclaimer |
| `enums.py` | Lifecycle and event type literals |
| `models.py` | `SimulatedTrade`, events, overview, snapshot |
| `eligibility.py` | Gate LONG/SHORT snapshots; derive entry limit; signal key |
| `entry_execution.py` | Post-decision limit fills + gap rules |
| `exit_execution.py` | SL/TP hits + same-candle ambiguity |
| `lifecycle.py` | Trade/event IDs and event append |
| `validation.py` | Quantity conservation |
| `simulator.py` | `TradeSimulator.process_tick` orchestration |

Integration: `ReplaySession` runs analysis, then `TradeSimulator.process_tick` on the closed 5m execution candle. REST under `/api/v1/replay/sessions/{id}/simulation/*`. WebSocket events on `/ws/replay` only.

Independent of live trading, exchange order APIs, and analysis algorithms. Does not generate signals.

## Trade state machine

States: `pending_entry` → `open` → `partially_closed` → `closed_tp` | `closed_sl` | `closed_expired`, plus `cancelled`, `rejected`, `ambiguous_execution`.

Every transition is timestamped via `SimulationExecutionEvent`.

## Eligibility

Eligible only when the snapshot decision is LONG or SHORT with a complete executable plan:

- Valid entry zone + derivable limit under configured entry policy
- Valid stop loss and take-profit levels
- Valid positive position size from the plan (never invented)
- Non-expired / non-invalidated lifecycle
- Spot never SHORT
- Futures LONG/SHORT only when the decision engine already allowed them

WAIT / NO TRADE / missing plan / invalid SL/TP / bad R:R / insufficient data → rejected or ignored.

Signal identity: `session|decision_id|plan_id|timestamp|exchange|market|symbol|direction`.

## Entry execution policy

Default: `exact_reference_price` (reuse `entry_zone.entry_reference_price`).

Also supported: `zone_boundary`, `zone_midpoint` (explicit only — never silent midpoint assumption).

If no valid entry price can be derived → reject.

Rules:

- Only candles with close time **strictly after** decision timestamp
- LONG: fill at open if open ≤ limit, else at limit when range crosses
- SHORT: fill at open if open ≥ limit, else at limit when range crosses
- Respect `expires_at`; unfilled → cancelled

## Exit execution

LONG: SL when `low ≤ stop`; TP when `high ≥ tp`.  
SHORT: SL when `high ≥ stop`; TP when `low ≤ tp`.

Gap: do not fill better than the opening price through the level.

## Partial take profits

Default allocations when plan has no sizes: TP1 40% / TP2 30% / TP3 30% (simulation defaults only). Sum must be 1.0. No automatic breakeven or trailing stops.

## Same-candle ambiguity

Default: `conservative_stop_first`.

Also: `mark_ambiguous`, `use_lower_timeframe_if_available` (historical lower TF only; no future data; if unresolved, remain ambiguous).

Never invent a favorable order without evidence.

## Quantity conservation

`original_quantity = remaining_quantity + quantity_closed_tp + quantity_closed_sl + quantity_closed_expired` within tolerance `1e-9`.

## Replay integration order

1. Advance clock  
2. Candle prefixes  
3. Historical analysis snapshot  
4. Eligibility / pending trade  
5. Pending entries on subsequent candles  
6. Open exits  
7. Lifecycle update  
8. Publish simulation snapshot  

Reset clears and rebuilds simulation deterministically. Speed does not change outcomes.

## REST API

- `POST .../simulation/enable` (also enables analysis)
- `POST .../simulation/disable`
- `GET .../simulation`
- `GET .../simulation/trades` (pagination + status filter)
- `GET .../simulation/trades/{trade_id}`
- `GET .../simulation/events`
- `POST .../simulation/reset`

## WebSocket (`/ws/replay`)

`simulation_enabled`, `simulation_disabled`, `simulation_snapshot`, `trade_pending`, `trade_opened`, `trade_partially_closed`, `trade_closed`, `trade_cancelled`, `trade_rejected`, `trade_ambiguous`, `simulation_error`.

Does not modify `/ws/market`.

## Frontend

Historical Replay page: Trade Simulation panel with counts (not performance), trade table, detail, chart legend levels. Future exit markers are hidden until the replay clock reaches them.

## Known limitations

- No fees, slippage models beyond gap rules, or P&L (Phases 5.2.3 / 5.2.4)
- Default lower TF equals execution TF (5m), so LTF path resolution is only useful when configured with a finer series
- OHLC path ambiguity remains for many same-candle cases under conservative policy
- Position size must already exist on the historical decision/plan

## Test results

Executed locally for this phase:

- Backend: **251 passed** (`pytest` full suite, including `tests/test_trade_simulation.py`)
- Frontend: **40 passed** (`npm test`, including `lib/simulation-display.test.ts`)
- Production build: **Next.js build succeeded**
