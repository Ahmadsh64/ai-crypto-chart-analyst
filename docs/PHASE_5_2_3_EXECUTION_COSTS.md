# Phase 5.2.3 — Fees, Slippage & Execution Cost Engine

Isolated cost layer that consumes Phase 5.2.2 simulated fills and computes estimated fees, slippage, spread, gross P&L, and net P&L.

**HISTORICAL SIMULATION — NOT REAL EXECUTION — COSTS ARE ESTIMATED**

Fee rates are user / environment / example assumptions — not verified live exchange fee schedules.

## Architecture

```
Replay → Historical Analysis (5.2.1) → Trade Simulation (5.2.2 fills)
                                              ↓
                                   Cost Engine (5.2.3)
                                              ↓
                              Execution Ledger → Gross/Net P&L
```

Package: `backend/app/replay/costs/`

Does **not** change analysis, entry/exit triggers, fill quantities, or lifecycle rules.

## Fee configuration

Version: `execution-costs-v1.0.0-balanced`

Sources (recorded on every ledger row):

| Source | Meaning |
|--------|---------|
| `user` | Set via REST config update |
| `environment` | `EXECUTION_COST_MAKER_FEE` / `EXECUTION_COST_TAKER_FEE` |
| `example_default` | Documented simulation examples only |

Example defaults (simulation only):

- Binance spot: maker/taker 0.001
- Binance USDT-M: maker 0.0002 / taker 0.0004
- Bybit spot: 0.001 / 0.001
- Bybit linear: 0.0002 / 0.00055

Configure your own account rates via the UI or API.

## Maker / taker

Estimated from fill context (not exchange-confirmed):

- Entry at exact limit → `maker` / limit
- Entry at open through limit (gap) → `taker` / marketable_limit
- Stop-loss exits → `taker` / stop
- TP at exact level → `maker`; gap through TP → `taker`
- Otherwise `unknown` + configurable fallback (`assume_taker` default)

## Slippage

Policies: `none` | `fixed_bps` | `percentage` | `conservative_ohlcv`

Adverse only. Adjusts **cost-layer execution price**; Phase 5.2.2 trigger/fill prices stay unchanged.

- LONG entry ↑ / LONG exit ↓
- SHORT entry ↓ / SHORT exit ↑

## Spread

Policies: `none` | `fixed_bps` | `percentage` | `synthetic_assumption`

Half-spread on entry and exit, adverse. Non-`none` policies are **synthetic** — not observed bid/ask.

## P&L formulas

LONG: `gross = (exit - entry) × qty × multiplier`  
SHORT: `gross = (entry - exit) × qty × multiplier`

Per exit:

`net = gross − allocated_entry_fee − exit_fee − exit_slippage − exit_spread`

Entry fees allocated proportionally by exit quantity / original quantity (once across partials).

Entry slippage/spread recorded on entry ledger rows and included in trade totals (not double-counted on exits).

## Ledger

Append-only; duplicate `source_event_id` rejected. IDs: `ec_{simulation_event_id}`.

## API

- `POST /api/v1/replay/sessions/{id}/costs/enable|disable|reset`
- `GET .../costs` · `GET .../costs/config` · `PUT .../costs/config`
- `GET .../costs/summary` · `GET .../costs/trades` · `GET .../costs/trades/{trade_id}`
- `GET .../costs/ledger`

Config updates rebuild the ledger; simulation fills are unchanged.

## WebSocket (`/ws/replay`)

`cost_model_enabled`, `cost_model_disabled`, `execution_cost_update`, `execution_ledger_update`, `trade_pnl_update`, `cost_model_error`

## Known limitations

- No historical bid/ask; spread is synthetic when enabled
- Maker/taker is estimated from OHLCV fill context
- Slippage does not alter 5.2.2 trigger conditions
- No win-rate / equity curve / drawdown (Phase 5.2.4+)
- Contract multiplier defaults to 1 unless configured

## Example

LONG 1 unit, entry 100 → exit 110, fees 0.1% both sides, no slip/spread:

- Gross = 10
- Entry fee ≈ 0.10, exit fee ≈ 0.11
- Net ≈ 9.79

## Test results (executed)

- Backend full suite: **274 passed**
- Frontend: **43 passed**
- Production build: **succeeded**
