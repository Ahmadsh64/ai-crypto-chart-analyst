# Phase 5.2.7 — Replay Seek API & Timeline Scrub Controls

## Purpose

Expose the existing `ReplaySession.seek` rebuild through REST and add timeline scrub controls to the Backtesting UI. No trading, analysis, simulation, execution-cost, analytics, or reporting formulas were changed.

## Endpoint

```
POST /api/v1/replay/sessions/{session_id}/seek
```

Response model: `ReplayControlResponse` (same shape as step / reset / speed).

### Request schema (`ReplaySeekRequest`)

Exactly one of:

| Field | Type | Meaning |
|-------|------|---------|
| `event_index` | integer | Target event index (clamped by session seek) |
| `timestamp` | ISO-8601 datetime (timezone required / parsed) | Latest event with `event_time <= timestamp` |

Examples:

```json
{ "event_index": 42 }
```

```json
{ "timestamp": "2024-01-01T12:00:00Z" }
```

### Timestamp mapping

Implemented by `event_index_at_or_before` in `app/replay/timeline.py` (UTC internally):

- Select the **latest** event whose time is **≤** the requested timestamp.
- Never select a future event.
- Timestamp **before** the first event → index `0` (aligned with negative index clamping).
- Timestamp **after** the last event → last index.
- Empty timeline → `ValueError` → HTTP **400**.

### Index clamping

`ReplaySession.seek` clamps into `[0, event_count - 1]`:

- Negative index → `0`
- Index beyond final event → last index
- Response reports the **resolved** `event_index` and `replay_timestamp`

### Error responses

| Condition | Status |
|-----------|--------|
| Unknown session | 404 |
| Empty timeline | 400 |
| Seek runtime error | 400 |
| Missing payload / both fields / bad types / malformed timestamp | 422 |

## Rebuild behavior

The endpoint calls `await session.seek(target)` only — no alternate rebuild path.

Established order (unchanged from Phase 5.2.5):

1. Replay clock and current event index
2. Historical analysis snapshot
3. Trade simulation
4. Execution costs and ledger
5. Performance analytics
6. Reporting reads the rebuilt state

Seeking backward drops future simulated trades, cost ledger entries, and analytics points tied to later clocks. Seeking forward rebuilds deterministically without duplicate fills or cost entries. Reset and step behavior are preserved.

## Frontend controls

`HistoricalReplayPanel` timeline scrubber:

- Shows current event index / total count and replay clock
- Range slider (commits on mouse/touch release or keyboard Home/End/arrows)
- Start / Middle / End buttons
- Disabled when no session or empty timeline
- Loading indicator while seeking
- `seekSeqRef` + `seekingRef` prevent overlapping seeks and ignore mid-seek WebSocket / stale panel refreshes
- On seek start, analysis / simulation / costs / analytics / report panels are cleared so future rows cannot linger
- Failed seek keeps prior snapshot and surfaces an error

Playback controls (start / pause / resume / step / reset / stop) are unchanged. `SimulationChartLegend` is unchanged. No chart trade markers in this phase.

## Known limitations

- Slider commits on release (not continuous drag) to avoid seek storms.
- Browser automation may not exercise native range-slider drag; Start / Middle / End buttons and REST seek are the reliable QA path.
- Seek rebuild with analysis + simulation + costs + analytics on long timelines can take seconds; overlapping seeks are sequenced and older responses discarded.
- Backend `--reload` clears in-memory sessions (seek then 404); the UI keeps the prior snapshot and restores scrub index on failure.
- Seek is still in-memory per session (no PostgreSQL / persistent sessions).
- Analysis history cache remains bounded (`max_history`); very long sessions may drop early cache entries (rebuild regenerates).
- Pre-existing Next.js hydration warning in `sidebar.tsx` is unrelated to seek math.

## Browser QA (Phase 5.2.7)

Workflow on `/backtesting` (BTC/USDT, ~6h window, analysis/sim/costs/analytics enabled):

1. Scrubber disabled before load — `docs/screenshots/qa-5-2-7-scrubber-disabled.png`
2. Middle seek → Event 36/71, clock + progress aligned — `docs/screenshots/qa-5-2-7-scrub-middle.png`
3. End seek → Event 71/71 Completed — `docs/screenshots/qa-5-2-7-scrub-end.png`
4. Backward middle → report clock `2026-11-14T08:29:59.999000Z` matches replay clock — `docs/screenshots/qa-5-2-7-report-clock-mid.png`
5. Start + Reset verified via automation (status Ready at event 1)

## Non-goals (confirmed)

No PostgreSQL, Alembic, formula changes, unrealized P&L, SimulatedTrade timeframe metadata, PDF redesign, chart trade markers, live trading changes, or Phase 6.
