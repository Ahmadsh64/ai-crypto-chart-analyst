# Phase 5.2.8 — Final Visual Browser QA Notes

**Fixture ID:** `fixture_phase528_trade_overlay_qa_v1`  
**Label:** LABELED_FIXTURE — test data only — NOT live trading evidence  
**Method:** CDP runtime injection into the live `/backtesting` `HistoricalReplayPanel` React state (no production source edits). Fixture trades/candles rendered through the real `CandlestickChart` overlay path.

## Clocks exercised

| Clock | Markers expected | Observed |
|-------|------------------|----------|
| before_entry | none | none |
| after_entry_before_tp1 | 2× LONG | 2× LONG; statuses OPEN |
| after_tp1_before_tp2 | LONG, TP1, SHORT, LONG | same; multi_tp PARTIALLY CLOSED; short OPEN |
| after_final_exit | LONG, TP1–3, SHORT, SL, LONG | 7 markers; no duplicate event ids |

Seek cycle final→open→final: deterministic marker sets; `noDupIds: true`.

## Screenshots

All under `docs/screenshots/` with `LABELED_FIXTURE_` prefix.
