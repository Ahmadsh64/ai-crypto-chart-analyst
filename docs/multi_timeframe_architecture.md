# Multi-Timeframe Data Orchestration (Phase 4.1)

Deterministic multi-timeframe candle orchestration. Prepares synchronized HTF→LTF context for later confluence — **no trade decisions in this phase**.

Configuration version: **`mtf-v1.0.0-orchestration`**

Depends on existing exchange adapters, candle normalization, and the centralized `/ws/market` hub. Does **not** modify Phase 3.1–3.4 calculation rules.

---

## Architecture

```
Exchange REST (Binance / Bybit)
        │
        ▼
ExchangeManager.fetch_ohlcv  ×  {4h, 1h, 15m, 5m}
        │
        ▼
MultiTimeframeOrchestrator
  · normalize / sort / dedupe
  · OHLC integrity
  · gap detection
  · closed vs forming separation
  · readiness / stale / quality
        │
        ├── REST  GET /api/v1/multi-timeframe
        └── WS    MultiTimeframeRuntime → multi_timeframe_update
                      ▲
                      │ candle_update (existing StreamManager)
```

One exchange WebSocket connection per `(exchange, market_type)`. MTF subscribes to four kline intervals on that same connection — no extra exchange sockets.

---

## Timeframe definitions

| Timeframe | Duration | Purpose |
|-----------|----------|---------|
| `4h` | 240 minutes | Higher timeframe context |
| `1h` | 60 minutes | Market structure context |
| `15m` | 15 minutes | Setup context |
| `5m` | 5 minutes | Entry confirmation context |

All timestamps are timezone-aware **UTC**. Exchange, symbol, and market type are preserved and never mixed across series.

---

## Synchronization strategy

Timeframes **do not** close simultaneously.

Example: a `5m` candle can be fully closed while the parent `15m` candle is still forming. The orchestrator:

1. Evaluates each timeframe independently against wall-clock UTC.
2. Marks a candle confirmed only when `is_closed` is true (exchange close / inferred close `< now`).
3. Keeps forming candles in a separate field (`forming_candle`).
4. Never promotes a forming candle into the confirmed series.
5. Never uses a candle with open time (or close time) in the future as confirmed history.

`sync.as_of` is the snapshot clock. Confirmed candles satisfy `timestamp ≤ as_of` and `is_closed`.

---

## Candle confirmation rules

| Rule | Behavior |
|------|----------|
| Confirmed | Closed candles only (`is_closed=true`) |
| Forming | At most one open candle per timeframe; excluded from confirmed series |
| Future leakage | Candles with `timestamp > as_of` or `close_time > as_of` are rejected from confirmed |
| Dedup | One candle per open timestamp (last write wins) |
| Order | Ascending by open timestamp |
| OHLC | Reuses `Candle` / `is_valid_ohlc` validation |

---

## Data quality rules

Per timeframe status:

| Field | Meaning |
|-------|---------|
| `is_ready` | Enough **closed** candles (`≥ min_closed_candles`) and no hard error |
| `is_stale` | Latest closed candle older than `stale_intervals × timeframe duration` |
| `has_data_gaps` | Adjacent open times exceed `1.5 ×` expected step |
| `data_quality` | `ok` \| `insufficient` \| `stale` \| `gaps` \| `error` \| `unavailable` |
| `status_detail` | Human-readable reason when not ok |

Overall snapshot:

- `ready` — all four timeframes ready
- `partial` — at least one ready, others failed/insufficient/stale
- `unavailable` — none ready

**Never substitute** one timeframe for another. A missing `15m` series stays unavailable; `5m` is not used as a stand-in.

---

## Historical limits (defaults)

| TF | Fetch limit | Min closed for ready |
|----|-------------|----------------------|
| 4h | 300 | 50 |
| 1h | 500 | 50 |
| 15m | 500 | 50 |
| 5m | 500 | 50 |

In-memory only for Phase 4.1 (compatible with future Redis/PostgreSQL). No new DB dependency.

---

## REST API

`GET /api/v1/multi-timeframe?exchange=binance&symbol=BTC/USDT&market_type=spot`

Response highlights:

- Identity: exchange, symbol, market_type
- `calculated_at`, `config_version`
- `overall_status`, `ready_timeframes`, `unavailable_timeframes`
- `timeframes`: map/list of per-TF summaries (counts, latest closed, quality, gaps)
- `sync`: as_of, per-TF latest closed times, alignment notes
- Optional compact recent closed candles (bounded) — not raw exchange payloads

---

## WebSocket events

| Client action | Server message |
|---------------|----------------|
| `subscribe_multi_timeframe` | Snapshot `multi_timeframe_update` (`kind=snapshot`) |
| candle fan-in (4 TFs) | `multi_timeframe_update` (`kind=update`) |
| `unsubscribe_multi_timeframe` | `unsubscribed` |

Payload distinguishes:

- `confirmed_candle` — closed bar update for that TF
- `forming_candle` — open bar update (never treated as confirmed)

Reconnect: runtime re-seeds from REST fetch and re-emits snapshot; deterministic series keys prevent duplicate state.

---

## Error handling

| Condition | Result |
|-----------|--------|
| Exchange timeout / HTTP error | That TF: `data_quality=error`, `status_detail` set; others still computed |
| Empty series | `unavailable` / `insufficient` |
| Invalid OHLC rows | Dropped at normalize; gaps may appear |
| WS disconnect | StreamManager reconnect; MTF runtime waits for next candle / resubscribe snapshot |

---

## No-lookahead guarantees

1. Confirmed history at `as_of` uses only candles with `is_closed` and `timestamp ≤ as_of`.
2. Forming candles are never included in `closed_candles`.
3. Incremental WS updates apply a closed candle to confirmed state only when `is_closed=true`.
4. Downstream Phase 4.2+ engines must consume confirmed series from this snapshot — not raw forming bars — for historical analysis.

---

## Known limitations

- No confluence scoring or LONG/SHORT/WAIT decisions (Phase 4.2+).
- No Redis/PostgreSQL candle cache yet.
- Gap detection is interval-heuristic; exchange maintenance holes are flagged, not filled.
- Chart Analyzer MTF view is an overview of data readiness, not multi-pane charting.
- StreamManager may subscribe multiple kline intervals per symbol on one exchange connection (by design for MTF).

---

## Out of scope (later)

Confluence scoring, trade signals, entries, stops, targets, risk, AI decisions.
