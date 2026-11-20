# Phase 5.2.5 — Backtesting Robustness & Validation

## Purpose

Strengthen reliability, determinism, data integrity, and historical correctness of the backtesting pipeline after approved Phases 5.1–5.2.4.

This phase does **not** change strategy formulas, execution-cost math, or analytics methodology except where a reproducible defect was found and fixed at the replay boundary.

## Pipeline (actual)

```
Historical OHLCV (exchange adapter + sanitize)
  → Replay timeline (5m event clock)
  → Analysis prefix (closed candles only, close_time <= T)
  → Decision / trade plan
  → Trade simulation
  → Execution costs
  → Performance analytics
```

### Stateful components / caches

| Component | State | Rebuild on reset | Rebuild on seek |
|-----------|-------|------------------|-----------------|
| `ReplaySession.series_by_tf` | Immutable after load | Kept | Kept |
| `event_times` / `event_index` | Clock | Index → 0 | Index → target |
| `_analysis_by_index` | Immutable per index | Pointer to 0; history kept | Reuse cache; pointer fixed |
| `TradeSimulator` | Trades / events | Full reset + rebuild | Full rebuild 0..T |
| `CostEngine` ledger | Entries | Reset + rebuild | Rebuild from trades |
| `AnalyticsEngine` | Snapshot cache | Reset + recompute | Recompute from sim+costs |

### Closed vs forming

- Closed: `candle_close_time(c, tf) <= replay_timestamp`
- Forming: built from closed 5m parts inside the open HTF/LTF bar; never uses future OHLC
- HTF bars become confirmed only at their own close time

### Duplicate / future prevention

- `sanitize_series` dedupes by open time, sorts chronologically, drops invalid / misaligned opens
- `filter_closed_prefix` / `assert_no_future_candles` reject future bars
- Simulation skips already-processed event indices (`_simulation_last_index`)
- Analysis cache is immutable per event index

## Changes in this phase

1. **Integrity hardening** (`timeline.py`, `normalizer.py`)
   - Reject non-finite volume (NaN/Inf) and negative volume
   - Drop TF-misaligned open timestamps (UTC boundary check)
   - Prefer closed duplicate when replacing an open duplicate

2. **Seek rebuild correctness** (`session.py`)
   - Seek with costs/analytics enabled always rebuilds the sim stack
   - After cache-only rebuild, `current_analysis` is forced to the seek target (fixes stale pointer after seek-away-and-back)

3. **Robustness helpers** (`replay/robustness/`)
   - Series integrity classification (continuous / gaps / invalid / incomplete / unavailable)
   - Pagination merge validation
   - Deterministic fingerprints for analysis / simulation / costs / analytics

4. **Tests & QA**
   - `tests/test_backtesting_robustness.py`
   - `scripts/qa_phase_5_2_5_api.py`

## Known limitations

- **No REST seek endpoint** — seek is session-method / test-only (`POST .../seek` → 404). UI uses step/reset/play.
- **Analysis history cache** is bounded (`max_history`); very long sessions may drop early cache entries (rebuild regenerates).
- **Live exchange windows** in the UI are not the source of unit-test fixtures; labeled synthetic series are used for determinism proofs.
- Frontend `__qaReplay` hooks exist for automation but are **not** treated as normal user interaction.
- Pre-existing Next.js hydration warning in `sidebar.tsx` observed during browser QA (unrelated to replay math).

## Non-claims

- Does not assert strategy profitability.
- Does not start Phase 5.2.6.
- Does not add live order execution or exchange trading keys.
