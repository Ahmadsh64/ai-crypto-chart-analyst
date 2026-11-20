# Phase 5.3.1 — Pre-Implementation Audit

## Relevant files

| Area | Path |
|------|------|
| Phase 5.3 mapper | `frontend/lib/trade-plan-chart-visuals.ts` |
| Phase 5.3 tests | `frontend/lib/trade-plan-chart-visuals.test.ts` |
| Overlay UI | `frontend/components/charts/trade-plan-chart-overlay.tsx` |
| Chart panel | `frontend/components/charts/market-chart-panel.tsx` |
| Chart core | `frontend/components/charts/candlestick-chart.tsx` |
| Page | `frontend/app/(app)/chart-analyzer/page.tsx` |
| Live store | `frontend/stores/live-market-store.ts` |
| Types | `frontend/types/api.ts` (`TradePlanResponse`, `DecisionResponse`, `Candle`) |

## Existing data sources

**Plan / decision (backend SoT):**
- Entry: `entry.entry_reference_price`, plus `entry_low` / `entry_high` / `price_inside_zone`
- SL: `stop_loss.stop_loss_price`
- TPs: `take_profit_targets[]` or decision `take_profit_prices[]`
- Direction, decision, `plan_id`, `decision_id`, `analysis_timestamp`, validation/eligibility

**Market price:**
- Live ticker `last` (WS) preferred
- Live candle `close` / forming OHLC
- REST candles `latest_price` / last close as seed

**Candles for touch detection:**
- REST `Candle`: `open/high/low/close`, `timestamp`, `is_closed`, optional `close_time`
- Live forming candle: `LiveCandle` with `isClosed`, OHLC, `processedAt`

**Freshness / connection:**
- `connectionStatus`: from market websocket store (`connected` / reconnecting / disconnected variants)
- `liveTicker.source`: `websocket` | `rest-fallback`
- `processedAt` / `last_updated` timestamps available
- Panel already shows `LIVE` vs `REST seed` and `forming`

## Current update flow

1. Market selection → REST seed candles + Decision/Trade Plan queries
2. WS subscriptions update live ticker/candle + decision/trade plan stores
3. `resolveTradePlanVisualSource` merges live over REST
4. `buildTradePlanChartVisuals` → price lines + RR zones
5. `CandlestickChart` syncs lines via `createPriceLine` / `applyOptions` (no chart recreate)
6. Stale plan protection via `analysis_timestamp` + market key

## Available fields for Phase 5.3.1

- Current price, entry, SL, TP1–3
- Entry zone low/high + `price_inside_zone` (backend-supplied)
- Direction (`bullish`/`bearish`) and decision state
- Candle high/low + closed vs forming
- Connection + processed timestamps

## Missing information (must not invent)

- Verified exchange fills / TP or SL execution — **not available**
- External notification channels — out of scope
- Exact exchange-side “touch fill” — only OHLC range touch visualization

## Proposed presentation calculations (frontend only)

| Metric | Formula |
|--------|---------|
| Distance to entry | `current - entry` (abs + % of entry) |
| LONG TP progress | `((current - entry) / (target - entry)) * 100` |
| SHORT TP progress | `((entry - current) / (entry - target)) * 100` |
| SL proximity | compare `|current - sl|` to fractions of `|entry - sl|` (50%/25%/10%) |
| TP proximity | same pattern toward each target |
| Touch | `candle.low <= level <= candle.high` |
| Freshness | map connection + age of `processedAt` → LIVE / DELAYED / STALE / DISCONNECTED / UNAVAILABLE |

## Risks

- Floating-point equality at levels → use small absolute/relative epsilon; never claim execution
- Forming candle touches are provisional only
- Stale/disconnected prices must not drive alerts or progress
- Highlighting selected lines must not recreate chart or duplicate lines
- Dense chart already has SMC overlays — keep monitor panel compact off-chart
- Must not break Phase 5.3 toggles / stale-plan watermark / 5.2.8 replay overlays

## Implementation plan

1. New pure module `trade-plan-monitor.ts` for distance, progress, proximity, touch, alerts, freshness.
2. Extend visual source with optional entry zone fields (compatible; no formula changes).
3. New `TradePlanMonitor` UI panel under chart overlays.
4. Chart interaction: selected level id → thicker/brighter price line via existing sync.
5. Optional proximity highlight on approaching levels (respect toggles).
6. Wire from `MarketChartPanel` using existing live price + candles.
7. Unit tests (all listed cases) + keep 5.3 tests intact.
8. Browser QA with labeled fixtures + screenshots + phase docs.
