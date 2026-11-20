# Phase 5.3.1 — Advanced Trade Plan Visualization & Smart Price Tracking

## Pre-audit

See `docs/PHASE_5_3_1_PRE_AUDIT.md`.

## Architecture

Presentation-only monitor layer on top of Phase 5.3 plan visuals:

1. Backend Decision / Trade Plan remain SoT for levels and direction.
2. Market price from existing ticker / live candle / REST seed (no second WS).
3. Pure module `trade-plan-monitor.ts` computes distance, PRICE PROGRESS, proximity, touches, freshness, alerts.
4. `TradePlanMonitorPanel` renders the compact Trade Plan Monitor.
5. Chart interaction: selecting a level highlights the matching price line via `applyPlanLineHighlights` (no chart recreation, no duplicate lines).
6. Alert dedupe keys: `planId|symbol|level|alertType`; reset on plan/market change; suppressed when freshness is not LIVE/DELAYED.

## Data sources

- Plan levels: existing Trade Plan / Decision REST + WS
- Entry zone: `entry_low` / `entry_high` / `price_inside_zone` (when supplied)
- Price: live ticker `last`, forming candle, REST seed
- Candles: REST OHLC + `is_closed`; live forming candle
- Freshness: `WsConnectionStatus` + `processedAt` age + source

## Calculation definitions

### Distance to Entry

- Absolute: `current - entry`
- Percent: `(current - entry) / entry * 100`
- Status: ABOVE / BELOW / AT PLANNED ENTRY / INSIDE ENTRY ZONE / UNAVAILABLE

### TP PRICE PROGRESS

- LONG: `((current - entry) / (target - entry)) * 100`
- SHORT: `((entry - current) / (entry - target)) * 100`
- Zero denominator → UNAVAILABLE
- Numeric progress is **not** silently capped
- Beyond target → `PRICE ABOVE TARGET LEVEL` / `PRICE BELOW TARGET LEVEL`
- Never labeled as realized profit / fill / completion

### SL proximity

Compare `|current - sl|` to `|entry - sl|` with UI thresholds 50% / 25% / 10%.  
Beyond SL → warning: `PRICE CROSSED PLANNED STOP LOSS LEVEL — EXECUTION NOT VERIFIED`

### TP proximity

Same span logic toward each target: FAR / APPROACHING / NEAR TARGET / AT / BEYOND.

### Touch detection

`candle.low <= level <= candle.high`  
Forming → `POSSIBLE TOUCH — FORMING CANDLE`  
Closed → `PRICE LEVEL TOUCHED — CLOSED CANDLE`  
Future candles ignored. No execution inference.

### Market-data freshness

LIVE / DELAYED / STALE / DISCONNECTED / RECONNECTING / UNAVAILABLE  
Alerts only when LIVE or DELAYED.

## Files created

| Path | Role |
|------|------|
| `docs/PHASE_5_3_1_PRE_AUDIT.md` | Audit |
| `docs/PHASE_5_3_1_ADVANCED_TRADE_PLAN_MONITORING.md` | This doc |
| `docs/qa-artifacts/phase-5-3-1/QA_BROWSER_VISUAL_NOTES.md` | Browser QA |
| `frontend/lib/trade-plan-monitor.ts` | Pure metrics |
| `frontend/lib/trade-plan-monitor.test.ts` | Unit tests |
| `frontend/components/charts/trade-plan-monitor-panel.tsx` | Monitor UI |

## Files modified

| Path | Change |
|------|--------|
| `frontend/lib/trade-plan-chart-visuals.ts` | Entry zone fields on visual source |
| `frontend/lib/trade-plan-chart-visuals.test.ts` | Fixture fields for zone |
| `frontend/components/charts/market-chart-panel.tsx` | Monitor wiring, highlights, QA price/freshness |

## Tests

`npm test`: **126 pass / 0 fail** (includes Phase 5.3 suite intact + new monitor cases).

## Browser QA

Completed on live `/chart-analyzer` with labeled fixtures. See QA notes.

## Screenshots

- `docs/screenshots/LABELED_FIXTURE_phase531_trade_plan_monitor.png`
- `docs/screenshots/LABELED_FIXTURE_phase531_long_progress.png`
- `docs/screenshots/LABELED_FIXTURE_phase531_short_progress.png`
- `docs/screenshots/LABELED_FIXTURE_phase531_stop_loss_warning.png`
- `docs/screenshots/LABELED_FIXTURE_phase531_tp_proximity.png`
- `docs/screenshots/LABELED_FIXTURE_phase531_price_level_touch.png`
- `docs/screenshots/LABELED_FIXTURE_phase531_stale_market_data.png`
- `docs/screenshots/LABELED_FIXTURE_phase531_no_trade_cleanup.png`

## Limitations

- Progress bar UI is visually capped at 0–100% for readability; numeric label remains uncapped.
- Touch detection uses available OHLC only; not exchange fill confirmation.
- Dense SMC overlays may still compete with plan lines on the chart itself.
- QA inject hook is fixture-only.

## Confirmations

- Existing trading formulas (Confluence / Trade Plan / Decision) were **not** modified.
- No trade execution introduced.
- Phases 5.2.2–5.3 remain intact (compatible extensions only).
- Phase 5.4 / 6 not started.
