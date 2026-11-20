# Phase 5.3 — AI Chart Analyzer Trade Plan Visualization

## Objective

Display the current Decision Engine + Trade Plan Engine levels on the live AI Chart Analyzer candlestick chart as **planned** overlays (Entry, Stop Loss, TP1–TP3, optional risk/reward zones), with visibility controls and decision-state behavior. Visualization only — no order execution and no recalculation of trading formulas in the frontend.

## Architecture

1. Backend remains the source of truth for Decision / Trade Plan payloads (REST + existing WS subscriptions).
2. Frontend normalizes live + REST payloads via `resolveTradePlanVisualSource`.
3. Pure mapper `buildTradePlanChartVisuals` converts valid levels into `TradeChartPriceLine` + `ZoneDrawSpec` (no execution markers).
4. `MarketChartPanel` applies lines/zones to the existing `CandlestickChart` instance without recreating the chart.
5. Toggle state is independent of analysis logic; live updates replace prices while preserving unrelated chart state.
6. Stale protection uses `analysis_timestamp` + market key (`exchange:marketType:symbol`).

## Files created

| Path | Role |
|------|------|
| `docs/PHASE_5_3_PRE_AUDIT.md` | Pre-implementation audit |
| `docs/PHASE_5_3_AI_CHART_ANALYZER_TRADE_PLAN_VISUALIZATION.md` | This document |
| `docs/qa-artifacts/phase-5-3/QA_BROWSER_VISUAL_NOTES.md` | Browser QA notes |
| `frontend/lib/trade-plan-chart-visuals.ts` | Pure visualization mapper |
| `frontend/lib/trade-plan-chart-visuals.test.ts` | Unit tests (18) |
| `frontend/components/charts/trade-plan-chart-overlay.tsx` | Controls, legend, status badge |

## Files modified

| Path | Change |
|------|--------|
| `frontend/components/charts/candlestick-chart.tsx` | Optional `planZones` merged into zone primitive; early-return allows plan-only zones |
| `frontend/components/charts/market-chart-panel.tsx` | Decision/Trade Plan wiring, toggles, legend, stale watermark, QA inject hook |
| `frontend/app/(app)/chart-analyzer/page.tsx` | `enableTradePlanVisuals` + sidebar plan-level mirror |

## API data sources

- `GET` trade-plan + decision (existing hooks)
- WS `trade_plan_update` / `decision_update` (existing subscriptions)
- No new API contracts
- No backend formula changes

## Chart visualization design

- Horizontal price lines via existing `createPriceLine` sync (`tradePriceLines`)
- Dashed planned styles; Entry amber, SL red, TP greens
- WAIT labels: `PLANNED ENTRY/STOP LOSS/TPn`
- LONG/SHORT labels: `ENTRY` / `STOP LOSS` / `TPn` with setup-confirmed status
- Risk/reward translucent zones via existing `ZonePrimitive`
- Current market price continues through existing ticker/live candle path (no second WS)

## Planned vs executed

- Planned levels never emit series markers / fill markers
- Legend explicitly marks Entry/SL/TP as **Planned**
- Disclaimer: “not exchange fills”
- Phase 5.2.8 historical execution markers remain replay-only and untouched

## Decision state behavior

| Decision | Visualization |
|----------|---------------|
| WAIT + valid plan | Planned levels + `WAITING FOR CONFIRMATION` |
| LONG + valid plan | Levels + `LONG SETUP CONFIRMED` |
| SHORT + valid plan | Levels + `SHORT SETUP CONFIRMED` (analysis-only; spot restrictions preserved) |
| NO TRADE | Clear all plan levels |
| Missing / invalid / blocked plan | `PLAN UNAVAILABLE`, clear levels |

## Controls

Show/Hide: Entry, SL, TP1, TP2, TP3, Risk/Reward zones, All trade plan levels (+ Show all / Hide all). Toggles update lines without recreating the chart.

## Stale-data protection

- Market key mismatch clears incompatible levels
- Strictly older `analysis_timestamp` for the same market is rejected
- Panel retains last applied visuals when a stale payload is ignored
- Symbol/exchange/market-type changes reset the watermark

## Tests performed

Frontend unit suite (`npm test`): **89 pass / 0 fail** (includes **18** new Phase 5.3 tests + Phase 5.2.8 regressions).

## Browser QA results

Completed on live `/chart-analyzer` with labeled CDP fixtures. See `docs/qa-artifacts/phase-5-3/QA_BROWSER_VISUAL_NOTES.md`.

## Screenshots

- `docs/screenshots/LABELED_FIXTURE_phase53_wait_long_planned_levels.png`
- `docs/screenshots/LABELED_FIXTURE_phase53_long_planned_levels.png`
- `docs/screenshots/LABELED_FIXTURE_phase53_short_planned_levels.png`
- `docs/screenshots/LABELED_FIXTURE_phase53_no_trade_cleared.png`
- `docs/screenshots/LABELED_FIXTURE_phase53_visualization_controls.png`
- `docs/screenshots/LABELED_FIXTURE_phase53_updated_plan_after_analysis.png`

## Limitations

- Dense SMC/OB-FVG overlays can visually compete with plan lines; toggles exist to reduce clutter.
- QA fixture hook (`window.__PHASE53_TRADE_PLAN_QA__`) is for labeled browser verification only.
- Spot SHORT remains analysis visualization only — no sell-short execution path.

## Confirmations

- Existing Decision / Trade Plan formulas were **not** modified.
- No trade execution, broker auth, or order placement was introduced.
- Phases 5.2.2–5.2.8 behavior (simulation, costs, analytics, reporting, seek, historical trade markers) was not modified.
- Phase 5.4 / Phase 6 were not started.
