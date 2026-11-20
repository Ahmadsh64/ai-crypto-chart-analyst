# Phase 5.3.1 — Browser Visual QA Notes

**Label:** `LABELED_FIXTURE — TEST DATA — NOT LIVE TRADING EVIDENCE`  
**Method:** Live `/chart-analyzer` + CDP via `window.__PHASE53_TRADE_PLAN_QA__` (`injectSource`, `setPrice`, `setFreshness`). Candles remain live; prices/plans are fixtures. Not live trading evidence.

## Scenarios

| Scenario | Result |
|----------|--------|
| LONG below Entry | `BELOW PLANNED ENTRY`; negative PRICE PROGRESS |
| LONG above / at Entry | `ABOVE` / `INSIDE ENTRY ZONE` |
| SHORT above Entry | `ABOVE PLANNED ENTRY` |
| SHORT below Entry | Positive TP progress toward lower targets |
| TP1/TP2/TP3 progress | Uncapped % labels; visual bar capped for display only |
| Approaching SL | `APPROACHING SL` |
| Beyond SL | `PRICE BEYOND SL LEVEL` + execution-not-verified warning |
| TP approaching | `APPROACHING` proximity |
| Forming / closed touch | `POSSIBLE TOUCH — FORMING CANDLE` / `PRICE LEVEL TOUCHED — CLOSED CANDLE` |
| Stale market data | Freshness `STALE`; no proximity alerts |
| NO TRADE | Monitor idle; legend levels cleared |
| Symbol / plan replace | Covered via inject + market-key reset path |
| Existing toggles | Controls remain below monitor |

## Screenshots

Under `docs/screenshots/`:

- `LABELED_FIXTURE_phase531_trade_plan_monitor.png`
- `LABELED_FIXTURE_phase531_long_progress.png`
- `LABELED_FIXTURE_phase531_short_progress.png`
- `LABELED_FIXTURE_phase531_stop_loss_warning.png`
- `LABELED_FIXTURE_phase531_tp_proximity.png`
- `LABELED_FIXTURE_phase531_price_level_touch.png`
- `LABELED_FIXTURE_phase531_stale_market_data.png`
- `LABELED_FIXTURE_phase531_no_trade_cleanup.png`
