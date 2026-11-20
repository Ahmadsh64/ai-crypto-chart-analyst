# Phase 5.2.1 — Historical Analysis Pipeline

Connects Phases 3.1–4.4 deterministic engines to the Phase 5.1 Historical Replay Engine so the platform can reconstruct what it would have known and concluded at every historical moment.

**No fills, fees, slippage, or P&L.** Phase 5.2.2 is not started.

## Architecture

```
ReplaySession (clock advance)
    │
    ▼
build_historical_prefixes  → closed candles only (close_time <= clock)
    │ validate no future bars
    ▼
calculate_indicators (3.1)     [per TF]
build_analysis_context_from_candles  [no ExchangeManager]
    ├── evaluate_timeframe_series + build_snapshot (4.1)
    ├── analyze_bundle → structure / liquidity / OB-FVG (3.2–3.4)
    └── analyze_confluence (4.2)
analyze_trade_plan (4.3)
analyze_decision (4.4)
    │
    ▼
HistoricalAnalysisSnapshot (compact, immutable per event index)
    └── /ws/replay → replay_analysis_update
```

Live REST `compute_*_response` paths are **not** used during replay (they fetch live OHLCV).

## Existing engines reused

| Stage | Function | Network |
|-------|----------|---------|
| Indicators | `calculate_indicators` | none |
| Structure / Liquidity / OB-FVG | `analyze_bundle` → `analyze_*` | none |
| MTF | `evaluate_timeframe_series`, `build_snapshot` | none |
| Confluence | `analyze_confluence` | none |
| Trade plan | `analyze_trade_plan` | none |
| Decision | `analyze_decision` | none |

New pure sibling: `build_analysis_context_from_candles` in `services/analysis_context.py` (live `build_analysis_context` unchanged).

## Historical context

`backend/app/replay/analysis/`:

- `context_builder.py` — explicit closed prefixes via `filter_closed_prefix`
- `validation.py` — `LookAheadError` if any candle closes after the clock
- `pipeline.py` — ordered engine run with `as_of=replay_timestamp`
- `snapshot.py` / `models.py` — compact immutable snapshots (no full candle arrays)

## No-look-ahead safeguards

1. Prefix construction at the pipeline boundary (never pass full series hoping engines ignore futures).
2. Defensive `assert_no_future_candles` on every TF prefix.
3. Forming bars are never marked confirmed.
4. MTF / confluence / plan / decision all receive `as_of=clock` (not wall clock).
5. Prefix-invariance test: analysis at T on prefix-only series ≡ analysis at T on full series with future appended.
6. Spot still never emits executable `SHORT`.

## Snapshot model

Per event index: decision, scores, evidence, conflicts, hypothetical entry/SL/TP/RR, indicator/structure/liquidity/OB summaries, closed counts, quality, analysis versions.

Earlier snapshots are never overwritten by later clocks. Cache key = event index.

## API

| Method | Path |
|--------|------|
| POST | `/api/v1/replay/sessions/{id}/analysis/enable` |
| POST | `/api/v1/replay/sessions/{id}/analysis/disable` |
| GET | `/api/v1/replay/sessions/{id}/analysis` |
| GET | `/api/v1/replay/sessions/{id}/analysis/history` |
| GET | `/api/v1/replay/sessions/{id}/analysis/at/{timestamp}` |

## WebSocket (`/ws/replay`)

- `replay_analysis_update` — lean decision/confluence/plan fields
- `replay_analysis_error` — analysis failure without killing the replay clock

Live `/ws/market` unchanged.

## Performance

- Event-index cache (deterministic reuse)
- `asyncio.to_thread` for CPU-bound pipeline so the event loop stays responsive
- Bounded history (`max_history`)
- Compact snapshots (counts/summaries, not full candle dumps)

## Frontend

Historical Replay page (`/backtesting`): Enable/Disable Historical Analysis + panel showing decision, scores, evidence, conflicts, hypothetical plan (explicitly labeled).

## Config version

`historical-analysis-v1.0.0`

## Known limitations

- Analysis on every max-speed tick can be CPU-heavy for long ranges (cache helps on reset/seek).
- Indicator set in snapshots is a compact subset of Phase 3.1 defaults.
- Does not simulate fills or equity (Phase 5.2.2+).
- Process-local session memory only.

## Test results

| Suite | Result |
|-------|--------|
| Backend `pytest` (Phases 1–5.2.1) | **220 passed** |
| Backend `tests/test_historical_analysis.py` | **9 passed** (look-ahead reject, prefix invariance, determinism, HTF gating, spot SHORT ban, API enable/history/reset) |
| Frontend `npm test` | **36 passed** |
| Frontend `npm run build` | **OK** |
| Live REST enable/step/history | **OK** |
| Browser QA `/backtesting` | **OK** — Enable Analysis → NO TRADE + HTF unavailable conflicts at early clock; panel updates with replay timestamp |
