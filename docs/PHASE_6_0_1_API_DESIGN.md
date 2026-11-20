# Phase 6.0.1 — API Design Proposal

**Not implemented.** Future routes under `/api/v1`. Existing live `/decision`, `/trade-plan`, `/ai/*`, `/replay/*` remain unchanged until explicitly versioned.

**Refinement 6.0.1.1:** `analysis_run_id`, consistency fields, idempotency conflict codes (409).

Common conventions:
- JSON only; ISO-8601 UTC timestamps.
- Financial numbers in JSON responses may be numbers **or** decimal strings for ledger/history exports; **persisted JSONB always uses decimal strings**.
- Pagination: `limit` (default 50, max 200), `offset`.
- Sorting: `sort=created_at|analysis_timestamp` + `order=asc|desc` (default desc).
- Errors: `{ "detail": "...", "code": "..." }`  
  - `409` + `code=IDEMPOTENCY_CONFLICT` when same id / different payload  
  - `409` + `code=DUPLICATE_LOGICAL_EVENT` when logical unique collides  
  - `422` semantic validation  
  - `503` database unavailable (live engines still work)

---

## A. Analysis History

### `GET /api/v1/history/analyses`
**Query:** `exchange`, `market_type`, `symbol`, `decision`, `consistency_status`, `analysis_run_id`, `from`, `to`, `limit`, `offset`, `sort`.  
**Response:** `{ items: AnalysisSnapshotSummary[], total, limit, offset }`  
Summary includes `analysis_run_id`, `consistency_status`, both provenance timestamps, decision-preferred levels.

### `GET /api/v1/history/analyses/{id}`
**Response:** Full detail including `snapshot_payload` (both raw decision/plan when present).  
**Errors:** 404.

### `GET /api/v1/history/analyses/by-run/{analysis_run_id}`
**Purpose:** Fetch the atomic snapshot+extracts for one Analyze orchestration.

### `POST /api/v1/history/analyses`
**Purpose:** Persist Decision+Trade Plan bundle from one orchestration.  
**Request:**
```json
{
  "analysis_run_id": "ar_…",
  "analysis_session_id": null,
  "exchange": "binance",
  "market_type": "spot",
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "decision": { "...DecisionResponse" },
  "trade_plan": { "...TradePlanResponse or null" }
}
```
**Server responsibilities:**
1. Validate `analysis_run_id` present (or generate if omitted — prefer client/orchestration-supplied).
2. Compute `consistency_status` per architecture rules (not merely shared run id).
3. Single TX insert snapshot + decision extract + plan extract.
4. Idempotent if same `analysis_run_id` + same `content_hash`; **409** if same run id / different hash.

**Response:** `201`/`200` with ids, `analysis_run_id`, `consistency_status`.

### `GET /api/v1/history/analyses/{id}/snapshot`
Raw immutable payload only.

---

## B. Trade Journal

### `GET /api/v1/journal`
**Query:** `simulated_trade_id`, `tag`, `from`, `to`, `limit`, `offset`.

### `POST /api/v1/journal`
`{ simulated_trade_id, title, notes?, setup_type?, tags?, lessons_learned? }` → `201`.  
Never modifies trade/ledger.

### `PATCH /api/v1/journal/{id}`
Metadata only.

### `DELETE /api/v1/journal/{id}`
`204` — journal metadata only; **no** financial cascade.

---

## C. Replay History

### `GET /api/v1/history/replay-sessions`
Filters: exchange, symbol, market_type, status, time range.

### `GET /api/v1/history/replay-sessions/{session_id}`
Persisted metadata + checkpoint.

### `GET /api/v1/history/replay-sessions/{session_id}/trades`
Query: `lifecycle_status`, pagination.

### `GET /api/v1/history/replay-sessions/{session_id}/trades/{trade_id}`
Trade + events; optional `include_ledger=true`.

### `GET /api/v1/history/replay-sessions/{session_id}/trades/{trade_id}/reconstruction-audit`
**Purpose:** Read-only compare materialized trade vs event/ledger reconstruction.  
**Response:** match boolean, diffs, warnings — **no repair**.

### `GET /api/v1/history/replay-sessions/{session_id}/reports`
List reports.

### `GET /api/v1/history/reports/{report_id}`
Full report payload.

### `GET /api/v1/history/replay-sessions/{session_id}/historical-analyses`
Paginated historical analysis snapshots.

---

## D. Saved Plans / Decisions

### `GET /api/v1/history/trade-plans`
Filters include `analysis_run_id`, `plan_status`, symbol, time.

### `GET /api/v1/history/trade-plans/{id}`
Full plan + parent snapshot link + `consistency_status` of parent.

### `GET /api/v1/history/decisions`
### `GET /api/v1/history/decisions/{id}`
Analogous; always expose `analysis_run_id`.

---

## E. Explicit non-goals

- No broker/order APIs.
- No silent overwrite of events/ledger on conflict.
- No requirement that OpenAI be available.
- Do not replace `/api/v1/replay/*` control plane until dual-read is designed.

## F. Error codes (persistence)

| HTTP | code | When |
|------|------|------|
| 409 | `IDEMPOTENCY_CONFLICT` | Same event_id/execution_id/analysis_run_id, different payload hash |
| 409 | `DUPLICATE_LOGICAL_EVENT` | Logical unique key collision |
| 422 | `CONSISTENCY_COMPUTE_FAILED` | Missing provenance for required fields |
| 503 | `DATABASE_UNAVAILABLE` | Persistence off/down; live analysis continues |
