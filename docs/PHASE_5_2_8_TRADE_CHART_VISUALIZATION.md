# Phase 5.2.8 — Interactive Trade Visualization & Chart Integration

## Purpose

Visualize **actual simulated trade fills and planned levels** on the Backtesting candlestick chart, synchronized with the historical replay clock.

This phase is **visualization-only**. Simulation, costs, analytics, and reporting formulas are unchanged.

## Overlay architecture

| Layer | Role |
|-------|------|
| `frontend/lib/trade-chart-visuals.ts` | Pure mapping: trades → markers + price lines (clock filter, dedupe) |
| `frontend/components/replay/historical-trade-overlay.tsx` | Toggle controls + trade details panel |
| `frontend/components/charts/candlestick-chart.tsx` | Applies markers via `createSeriesMarkers`; planned levels via `createPriceLine` |
| `HistoricalReplayPanel` | Builds visuals from simulation snapshot + replay clock; clears during seek |

Backend simulation remains the source of truth. The frontend does not recalculate fills or P&L.

## Event → marker mapping

| Simulation event | Marker |
|------------------|--------|
| `trade_opened` with fill price | LONG ↑ (green) or SHORT ↓ (red) |
| `trade_partially_closed` | `TP{n}` circle (cyan), `tp_index` 0-based → TP1… |
| `trade_closed` with stop reason | `SL` (orange) |
| `trade_closed` / other TP final | `TP{n}` or `EXIT` |
| `trade_pending` | No entry marker (not filled) |

Chart X uses `candle_open_time` when present (open-time UTC bar slot); otherwise event `timestamp`.

## Planned levels vs executed fills

- **Markers** = executed fills only (price + timestamp from events).
- **Price lines** = planned Entry / SL / TP values from `SimulatedTrade` fields (`entry_price` or `entry_limit_price`, `current_stop_loss`, `take_profit_levels`).
- Missing TP slots are not fabricated.
- Line titles include a short trade-id suffix so overlapping levels stay distinguishable.

## Replay clock filtering

For clock **T**:

- Hide trades with `decision_timestamp > T`.
- Hide rejected / cancelled trades.
- Include only `execution_events` with `timestamp <= T`.
- Derive status from filtered events: OPEN / PARTIALLY CLOSED / CLOSED / PENDING.
- A trade entered before T and exited after T appears **OPEN** at T (no future exit marker).

During seek (`seeking === true`), overlays are cleared until the new snapshot is applied so stale future markers cannot linger.

## Backward / forward seek

Works with Phase 5.2.7 REST seek and the scrubber:

1. Seek begins → clear selection + panel snapshots; chart overlays empty.
2. Session rebuild drops future trades server-side.
3. New snapshot → visuals recomputed for the new clock.
4. Forward seek restores markers deterministically; `event_id` dedupe prevents duplicates.

## Deduplication

`dedupeEventsById` keeps the first occurrence of each `event_id` when REST/WS replay the same event.

## UI controls

Toggles (persist across replay ticks):

- Entry markers
- Exit markers
- Partial exits
- Entry line
- Stop Loss line
- Take Profit lines

Click a marker → compact trade details (available fields only; future exit/P&L omitted). Realized P&L shown only when status at clock is CLOSED and `CostSnapshot` supplies `net_realized_pnl`.

## Known limitations

- Marker click uses chart click + proximity to marker price (Lightweight Charts has no per-marker click API).
- Dense trade clusters can overlap labels; toggles help declutter.
- Live BTC windows may produce few/no fills; unit tests use labeled fixtures.
- `closed_expired` exists on the enum but is not assigned by the current simulator.
- `SimulationChartLegend` text list is unchanged (still present under the chart).
- No PostgreSQL / Phase 6 persistence.

## Browser QA notes

Live BTC/USDT replay (2026-11-13 → 2026-11-14) with analysis + simulation enabled produced **0 simulated trades** (persistent NO TRADE / invalidated). Verified on live UI:

- Trade chart overlay toggles render and flip without recreating the page shell.
- Seek (End / Middle) updates the replay clock; overlays stay empty when no fills exist.
- Session reset / reload clears prior chart state.

**Marker / partial-TP / SL / clock-filter / dedupe / open-at-intermediate-clock** behaviors are verified by labeled fixtures in `frontend/lib/trade-chart-visuals.test.ts` (not live exchange fills).

Screenshot: `docs/screenshots/qa-5-2-8-trade-overlay-controls.png`
