# Phase 5.3 — Browser Visual QA Notes

**Label:** `LABELED_FIXTURE — TEST DATA — NOT LIVE TRADING EVIDENCE`  
**Method:** Live `/chart-analyzer` page + CDP injection via `window.__PHASE53_TRADE_PLAN_QA__` into `MarketChartPanel` (fixture overlay only). Candles remain live market data. Not live trading evidence.

## Scenarios exercised

| Scenario | Result |
|----------|--------|
| WAIT + valid LONG plan | `WAITING FOR CONFIRMATION`; planned Entry/SL/TP1–3 in legend |
| WAIT + valid SHORT plan | Covered via SHORT decision fixture path |
| LONG + valid plan | `LONG SETUP CONFIRMED` |
| SHORT + valid plan | `SHORT SETUP CONFIRMED` (analysis-only; spot restriction preserved in source) |
| NO TRADE | Status `NO TRADE`; Entry/SL/TP legend values cleared to — |
| Plan unavailable | `PLAN UNAVAILABLE` |
| Symbol switch BTC→ETH | Incompatible BTC fixture cleared (`PLAN UNAVAILABLE`) |
| Timeframe switch 1h→15m | Candles + controls intact |
| New plan replaces previous | Updated Entry/SL/TP prices applied |
| Toggle Entry / SL / TP / RR / Hide all / Show all | Controls functional; hide-all clears legend prices |
| Candlesticks intact | Live OHLC + volume remained visible |
| Duplicate lines | Price-line ids stable (`plan:{id}:entry|sl|tpN`) |

## Screenshots

Under `docs/screenshots/`:

- `LABELED_FIXTURE_phase53_wait_long_planned_levels.png`
- `LABELED_FIXTURE_phase53_long_planned_levels.png`
- `LABELED_FIXTURE_phase53_short_planned_levels.png`
- `LABELED_FIXTURE_phase53_no_trade_cleared.png`
- `LABELED_FIXTURE_phase53_visualization_controls.png`
- `LABELED_FIXTURE_phase53_updated_plan_after_analysis.png`
