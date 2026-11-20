# Phase 5.1 — Historical Replay Engine

Deterministic multi-timeframe historical candle replay foundation for the future Backtesting Engine (Phase 5.2+). **No trade simulation, fills, fees, or P&L in this phase.**

## Architecture

```
REST /api/v1/replay/sessions/*
        │
        ▼
ReplayManager (in-memory sessions)
        │
        ├── load_replay_series → ExchangeManager.fetch_ohlcv (Binance/Bybit adapters)
        ├── sanitize_series / build_event_timeline / snapshot_at
        └── ReplaySession (clock, controls, pacing task)
                │
                └── broadcast → /ws/replay (ReplayWebsocketHub)
```

Frontend: `/backtesting` route hosts the Historical Replay panel. Chart candles are taken from the current snapshot only (closed + forming). Live `/ws/market` is never used for replay.

## Timestamp convention

- Candle `timestamp` = **open time (UTC)** — same as exchange adapters / `Candle` model.
- Close time = `open + timeframe_duration − 1ms` (or API-provided `close_time`).
- A candle is **closed** at replay clock `T` iff `close_time <= T`.
- Forming HTF/LTF bars are aggregated from **closed 5m candles only** inside the current open interval. Final OHLC of an unfinished parent bar is never exposed.

## Replay lifecycle

1. `POST /sessions` — create session, paginated historical load, sanitize, build 5m-close event timeline, status `ready` (or `error` if empty).
2. `start` / `pause` / `resume` / `stop` — pacing runner uses wall-clock sleep for UI speed only; event order and OHLC are independent of wall clock.
3. `step` — advance one event deterministically.
4. `reset` — seek to event index 0.
5. `speed` — `1x`…`100x` / `max` (instant delay=0).
6. `DELETE` — stop runner and drop session.

## Multi-timeframe synchronization

Supported TFs: **4h, 1h, 15m, 5m**. Event clock ticks are **5m candle close times**. At each tick the snapshot includes per-TF closed counts, preview closed candles, forming candle (if any), readiness, and gap metadata. A 5m close does not mark 1h/4h as newly closed unless their own close time equals the clock.

## No-look-ahead safeguards

- Snapshots filter `close_time <= clock`.
- Forming candles never read unfinished parent-bar finals from the raw series.
- Prefix-equivalence test: state after replaying first N events equals state at the same index on the full timeline.
- Future liquidity / structure / OB / FVG / decisions are **not** computed in this phase.

## API endpoints

| Method | Path |
|--------|------|
| POST | `/api/v1/replay/sessions` |
| GET | `/api/v1/replay/sessions/{id}` |
| POST | `/api/v1/replay/sessions/{id}/start` |
| POST | `/api/v1/replay/sessions/{id}/pause` |
| POST | `/api/v1/replay/sessions/{id}/resume` |
| POST | `/api/v1/replay/sessions/{id}/stop` |
| POST | `/api/v1/replay/sessions/{id}/step` |
| POST | `/api/v1/replay/sessions/{id}/reset` |
| POST | `/api/v1/replay/sessions/{id}/speed` |
| DELETE | `/api/v1/replay/sessions/{id}` |

## WebSocket events (`/ws/replay`)

Dedicated channel (not `/ws/market`). Client: `{"action":"subscribe","session_id":"..."}`.

Events: `replay_connected`, `replay_subscribed`, `replay_started`, `replay_paused`, `replay_resumed`, `replay_stopped`, `replay_reset`, `replay_candle_update`, `replay_candle_closed`, `replay_snapshot`, `replay_completed`, `replay_error`.

## Historical data limitations

- Uses existing adapter pagination (≤1000/page) and rate limiting.
- Gaps detected; **no fabricated or interpolated candles**.
- Insufficient coverage → `data_quality` / `limitations` / session `error`.
- In-memory sessions only (no Redis/Postgres for Phase 5.1).
- Max candles per TF capped by `ReplayConfig.max_candles_per_timeframe`.

## Config version

`replay-v1.0.0`

## Test results

| Suite | Result |
|-------|--------|
| Backend `pytest` (full, incl. Phase 1–4.4 + 5.1) | **211 passed** |
| Backend `tests/test_replay.py` | **20 passed** (ordering, no-look-ahead, prefix-equivalence, controls, API, isolation, gaps/dupes/invalid OHLC, speed invariance) |
| Frontend `npm test` | **35 passed** (incl. 3 replay display helpers) |
| Frontend `npm run build` | **OK** (Next.js 16.4.5) |
| Live API create/step/delete (Binance spot BTC/USDT) | **OK** — chronological clock, MTF closed counts, `timestamp_convention=open_time_utc` |
| Browser QA `/backtesting` | **OK** — load → Ready → step advances progress; chart TF switch 1h→5m; no live WS used |

## Known limitations

- Replay sessions are process-local (lost on backend restart).
- Speed pacing uses `asyncio.sleep` — fine for UI; backtests should use `max` / seek.
- Chart preview returns a bounded recent closed window (`preview_closed_limit`), not the entire history payload every snapshot.
- Does not run Phase 3–4 analysis engines on historical prefixes yet (reserved for later phases).
- Phase 5.2 backtesting / fills intentionally not started.
