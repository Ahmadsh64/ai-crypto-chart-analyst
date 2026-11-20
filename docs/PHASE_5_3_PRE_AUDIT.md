# Phase 5.3 — Pre-Implementation Audit

## Existing architecture

- Route: `/chart-analyzer` → `frontend/app/(app)/chart-analyzer/page.tsx`
- Chart: `MarketChartPanel` → `CandlestickChart`
- Analysis panels: `TradePlanPanel`, `DecisionPanel` (text only; not on chart)
- Live candles: REST seed + `/ws/market` via `useLiveChartSubscription`
- Decision / Trade Plan: REST hooks + WS `decision_update` / `trade_plan_update`

## Relevant files

| Area | Path |
|------|------|
| Page | `frontend/app/(app)/chart-analyzer/page.tsx` |
| Chart wrapper | `frontend/components/charts/market-chart-panel.tsx` |
| Chart core | `frontend/components/charts/candlestick-chart.tsx` |
| Trade plan panel | `frontend/components/charts/trade-plan-panel.tsx` |
| Decision panel | `frontend/components/charts/decision-panel.tsx` |
| Types | `frontend/types/api.ts` (`TradePlanResponse`, `DecisionResponse`) |
| Phase 5.2.8 utils | `frontend/lib/trade-chart-visuals.ts` (SimulatedTrade / replay — not drop-in) |
| Zones | `frontend/lib/zone-primitive.ts` (`ZoneDrawSpec`) |

## API response structure (actual)

**TradePlanResponse:** `plan_id`, `plan_status` (`eligible`|`blocked`|`invalid`), `direction`, `entry.entry_reference_price` (+ zone low/high), `stop_loss.stop_loss_price`, `take_profit_targets[].{index,label,price,risk_reward_ratio}`, `risk.primary_rr`, `validation.is_valid`, `analysis_timestamp`, `spot_short_warning`.

**DecisionResponse:** `decision_id`, `decision` (`LONG`|`SHORT`|`WAIT`|`NO TRADE`), `lifecycle`, `trade_plan_status`, `trade_plan_id`, `entry_zone_summary`, `stop_loss_price`, `take_profit_prices[]`, `primary_rr`, `analysis_timestamp`, `spot_restriction`.

## Frontend data flow

1. Market store selects exchange / market / symbol / TF.
2. `MarketChartPanel` loads candles + structure/liquidity/OB-FVG overlays.
3. `useTradePlan` / `useDecision` seed REST; WS updates overwrite when present.
4. Panels render text; **chart never receives plan price lines today**.

Stale protection today: backend payload hash + client fingerprint. Prefer `analysis_timestamp` + `plan_id`/`decision_id` + market key for overlay sync.

## Chart capabilities

- `tradePriceLines` → `createPriceLine` (Phase 5.2.8)
- `tradeMarkers` → series markers (historical fills — **not** for planned live levels)
- `ZonePrimitive` → OB/FVG zones (reusable for risk/reward)

## Reusable vs not from 5.2.8

- **Reuse:** `TradeChartPriceLine` type + chart price-line sync; zone primitive; toggle UX pattern.
- **Do not reuse as-is:** `buildTradeVisuals` / fill markers / replay clock filtering / seek clears.

## Risks

- Mixing planned live levels with historical execution markers (must keep separate).
- Spot SHORT: decision will not emit executable SHORT; plan may still be hypothetical — respect `spot_restriction` / `spot_short_warning`.
- Dual sources (plan vs decision levels) must not invent missing TPs.
- OB/FVG zones and risk/reward zones share `ZonePrimitive` — merge carefully.
- Do not touch replay / 5.2.2–5.2.8 behavior.

## Proposed plan

1. New pure mapper `trade-plan-chart-visuals.ts` from Trade Plan + Decision → planned lines + RR zones + status.
2. Controls + legend UI on Chart Analyzer.
3. Extend `CandlestickChart` with optional `planZones` merged into zone drawing.
4. Pass lines/zones from `MarketChartPanel` / page.
5. Unit tests + browser QA with labeled fixtures if live states are sparse.
