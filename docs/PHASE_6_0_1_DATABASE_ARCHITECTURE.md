# Phase 6.0.1 — Database Architecture

**Status:** Design complete + integrity refinement (Phase 6.0.1.1)  
**Scope:** PostgreSQL persistence architecture only. No migrations, no ORM code, no API implementation in this phase.

## 1. Purpose

Introduce durable storage for:

| Domain | Existing runtime source (today) |
|--------|----------------------------------|
| Live analysis history | Ephemeral REST/WS responses |
| Decision / trade-plan history | `DecisionResponse`, `TradePlanResponse` |
| Saved analysis snapshots | AI `AnalysisSnapshot` + replay `HistoricalAnalysisSnapshot` |
| Replay sessions | In-memory `ReplayManager` / `ReplaySession` |
| Simulated trades & events | `SimulatedTrade`, `SimulationExecutionEvent` |
| Execution costs | `LedgerEntry`, `TradeCostSummary`, `CostSnapshot` |
| Analytics / backtest reports | `AnalyticsSnapshot`, `BacktestReportSnapshot` |
| Trade journal | **Not implemented** — greenfield design only |

PostgreSQL is a **storage and retrieval layer**. Deterministic Python engines remain the sole source of truth for calculations.

## 2. Repository audit summary

### 2.1 What exists

| Area | Location | Persistence today |
|------|----------|-------------------|
| Pydantic API schemas | `backend/app/api/schemas/*` | None |
| Decision / trade plan engines | `backend/app/analysis/*` | None |
| AI AnalysisSnapshot | `backend/app/ai/explainer/snapshot.py` | None (not Pydantic-frozen) |
| Replay sessions | `backend/app/replay/manager.py` | **In-memory dict** |
| Simulation | `backend/app/replay/simulation/models.py` | In-memory session state |
| Event IDs | `lifecycle.new_event_id()` | **Random** `se_` + uuid (not rebuild-safe) |
| Trade IDs | `lifecycle.new_trade_id()` | **Random** `st_` + uuid |
| Costs (Decimal) | `backend/app/replay/costs/models.py` | In-memory; `execution_id = ec_{event_id}` |
| Analytics / reports | `backend/app/replay/analytics/*`, `reporting/*` | In-memory / export artifacts |
| Config | `DATABASE_URL`; sqlalchemy/asyncpg/alembic in requirements | Not wired |
| Auth / users | Optional `X-API-Key` only | **No user identity system** |

### 2.2 Persist vs transient

| Persist (historical record) | Remain transient |
|-----------------------------|------------------|
| Decision / trade-plan response payloads at save time | Live WebSocket tick streams |
| Historical analysis snapshots at replay timestamps | Forming candles / live chart buffers |
| Replay session metadata + config versions | Full candle arrays in memory during active replay |
| Simulated trades + execution events | AI Vision image bytes |
| Cost ledger entries + cost config snapshot | OpenAI prompts / raw provider responses |
| Backtest report snapshots | Ephemeral UI state (panel toggles) |
| Manual trade journal notes | Live market ticker cache |

### 2.3 Carried Phase 5.4.1 / 6.0.1 limitations

1. Runtime `AnalysisSnapshot` is mutable → DB row must be **append-only immutable**.
2. Dual Decision/Trade-Plan fetch → persist with **`analysis_run_id` + provenance + consistency_status**; never claim ALIGNED solely because of shared run id.
3. OpenAI optional → no FK or required AI tables for core persistence.
4. Historical AI explanations unsupported.
5. Replay is in-memory → design persistence adapters without changing engines in 6.0.1.
6. **Current simulation event/trade IDs are random** → Phase 6.0.2+ must introduce **deterministic identity** for durable rebuild (documented below). Fill/ambiguity semantics stay unchanged.

## 3. Layered architecture (future)

```
FastAPI routes
    → application services (orchestration / DTO mapping)
        → repositories (SQLAlchemy async)
            → PostgreSQL
Deterministic engines (analysis / replay / sim / costs)
    → remain pure compute; called BY services, never call DB
```

Engines stay DB-free. Persistence façades own idempotency, hashing, and transactions.

### Transaction boundaries

| Operation | Boundary |
|-----------|----------|
| Save live analysis | **One TX:** optional `analysis_sessions` + `analysis_snapshots` + `decisions` + `trade_plans` (same `analysis_run_id`) |
| Simulation event apply | **One TX:** upsert `simulated_trades` + insert `trade_events` + insert matching `execution_cost_ledger` rows |
| Report generate | One TX: `backtest_reports` |
| Journal create/update/delete | One TX: journal row only — never touches trades/events/ledger |

## 4. Analysis run correlation (`analysis_run_id`)

### 4.1 Definition

- Generate **one** `analysis_run_id` per Analyze / save orchestration request (format: `ar_` + uuid hex, or UUID).
- Attach the **same** `analysis_run_id` to:
  - persisted `analysis_snapshots`
  - normalized `decisions` extract
  - normalized `trade_plans` extract
- Preserve original business IDs unchanged: `decision_id`, `plan_id` / `trade_plan_id`.
- Store separately:
  - `decision_analysis_timestamp`
  - `trade_plan_analysis_timestamp`
- `analysis_timestamp` on the snapshot = decision timestamp when present, else plan timestamp.

### 4.2 What `analysis_run_id` does **not** mean

Sharing an `analysis_run_id` **never** by itself proves market-context alignment. Classification uses `consistency_status` rules in §5.

### 4.3 Atomic save

Snapshot + decision extract + plan extract for one run are committed in a **single database transaction**. Partial saves are not allowed.

## 5. Consistency status rules

`consistency_status` ∈:

| Status | When |
|--------|------|
| `ALIGNED` | Both decision and plan payloads present **and** all alignment checks pass (§5.1) |
| `DUAL_FETCH_DIVERGED` | Both present **and** any alignment check fails |
| `DECISION_ONLY` | Decision present, plan absent/null |
| `PLAN_ONLY` | Plan present, decision absent/null |
| `INSUFFICIENT_PROVENANCE` | Required provenance timestamps missing, or exchange/symbol/market_type missing on either side |

### 5.1 ALIGNED checks (all required)

1. Same `exchange`, `market_type`, `symbol` (normalized).
2. Both `decision_analysis_timestamp` and `trade_plan_analysis_timestamp` present.
3. Absolute timestamp delta ≤ **2 seconds**.
4. **Comparable trading levels** (only when both sides have a value):
   - `entry_reference_price` within relative ε = `1e-8` (or absolute `1e-12` for near-zero).
   - `stop_loss_price` within same ε.
   - `take_profit` lists: same length; each index within ε (order preserved as engine-emitted).
5. Direction compatibility when both directional: plan direction maps consistently to decision LONG/SHORT (bullish↔LONG, bearish↔SHORT). WAIT/NO TRADE with a blocked/ineligible plan may still be ALIGNED on context/timestamps/levels if levels agree or are both empty.

### 5.2 Divergent snapshot handling

- Persist **both** original payloads under `snapshot_payload.raw_decision` and `snapshot_payload.raw_trade_plan`.
- Persist both timestamps and `consistency_status = DUAL_FETCH_DIVERGED`.
- **Never** silently average, pick-max, or otherwise merge conflicting Entry/SL/TP into a synthetic third set.
- Queryable NUMERIC extracts prefer **decision** values (matches current `build_analysis_snapshot`); plan-only fields remain in JSONB. Consumers must read `consistency_status`.

## 6. Trade event idempotency

### 6.1 Runtime gap (documented)

Today `backend/app/replay/simulation/lifecycle.py` generates random `event_id` / `trade_id`. That is **not** acceptable for durable replay restart/rebuild.

Phase 6.0.2+ persistence **requires** deterministic IDs (adapter and/or engine ID helper). Changing ID generation must **not** change fill prices, quantities, or `conservative_stop_first` ambiguity semantics.

### 6.2 Deterministic `trade_id` (for rebuild)

```
trade_id = "st_" + sha256_hex(
  "{replay_session_id}|{signal_key}|{decision_event_index}|{direction}"
)[:20]
```

Scoped uniqueness: globally unique in practice via session prefix; DB PK = `trade_id`.

### 6.3 Deterministic logical event identity

**Logical key components** (identity — do **not** include price/quantity):

| Field | Role |
|-------|------|
| `replay_session_id` | Session scope |
| `trade_id` | Trade scope |
| `event_type` | Lifecycle kind |
| `candle_open_time` | Preferred bar identity (UTC); fallback `event_timestamp` if null |
| `tp_index` | Distinguishes TP1/TP2/… partials (`NULL` → sentinel `-1`) |
| `reason` class (optional normalized) | Only if required to separate cancel vs reject of same type |

```
event_id = "se_" + sha256_hex(
  "{replay_session_id}|{trade_id}|{event_type}|{candle_open_time_iso}|{tp_index_or_-1}"
)[:24]
```

**Scope:** `event_id` is **globally unique** (hash embeds session+trade). Additionally enforce:

```sql
UNIQUE (replay_session_id, trade_id, event_type, candle_open_time, tp_index_key)
```

### 6.4 Canonical payload + conflict policy

`payload_hash` = SHA-256 of canonical JSON over:

- `price`, `quantity`, `remaining_quantity`, `reason`, `ambiguity_policy_applied`, `event_timestamp`, `metadata` (sorted keys)

On insert of `(event_id, payload_hash, …)`:

| Condition | Behavior |
|-----------|----------|
| No existing `event_id` | Insert |
| Same `event_id` + same `payload_hash` | **Idempotent success** (no-op / return existing) |
| Same `event_id` + different `payload_hash` | **Integrity conflict** — never overwrite |
| Same logical unique key + different `event_id` | **Integrity conflict** |

Repeated replay processing therefore cannot duplicate partial exits or stop-loss rows.

### 6.5 Transaction with trade state

Within one TX:

1. Lock/upsert `simulated_trades` by `trade_id`.
2. Try insert `trade_events`.
3. If idempotent duplicate → do **not** re-apply quantity transitions.
4. If new event → apply state transition to materialized trade row.
5. Insert ledger rows for fill-affecting events (idempotent on `execution_id`).

## 7. Simulated trade financial reconstruction

### 7.1 Authority split

| Store | Role |
|-------|------|
| `simulated_trades` | **Latest materialized state** (lifecycle, remaining qty, current SL, fill aggregates) |
| `trade_events` | **Append-only** execution/lifecycle history |
| `execution_cost_ledger` | **Append-only** fees/slippage/spread/gross/net at execution time + cost versions |

Planned Entry/SL/TP on the trade (`entry_zone`, `initial_stop_loss`, `take_profit_levels`) are **analytical levels**, never fills.

### 7.2 Event types that affect executed quantity

From `SimulationEventType` / cost role mapping:

| Event type | Quantity effect |
|------------|-----------------|
| `trade_opened` | Entry fill: increases `executed_quantity`; sets `entry_price`/`entry_timestamp`; `remaining_quantity = original` (or engine rule) |
| `trade_partially_closed` | Exit fill: decreases `remaining_quantity`; increments `quantity_closed_tp` (and `tp_filled`) |
| `trade_closed` (TP/SL/expired paths as encoded in status) | Final exit: remaining → 0; update closed_* aggregates |
| `trade_pending` / `trade_cancelled` / `trade_rejected` / `trade_ambiguous` | **No** fill quantity (unless accompanied by explicit fill fields — default: no) |
| `simulation_snapshot` / `simulation_error` | No quantity |

Partial exit update:

```
remaining_quantity := remaining_quantity - exit_qty
executed exit totals += exit_qty  (into tp/sl/expired buckets per reason)
```

Quantity conservation (audit):

```
original_quantity ≈ remaining_quantity
  + quantity_closed_tp + quantity_closed_sl + quantity_closed_expired
```

(within NUMERIC ε).

### 7.3 Cost allocation (matches existing cost engine)

- **Entry row:** fee/slippage/spread on entry; no gross/net usually.
- **Exit row:**  
  - `gross = (exit - entry) * qty` (LONG) or `(entry - exit) * qty` (SHORT) — see `gross_pnl()`.  
  - `allocated_entry_fee = total_entry_fee * exit_qty / original_qty` capped by remaining unallocated (`allocate_entry_fee`).  
  - `net = gross - allocated_entry_fee - exit_fee - exit_slippage - exit_spread` (`net_pnl()`).
- Store `cost_model_version`, `fee_config_source`, `fee_schedule_version`, rates, and amounts **on the ledger row at write time**.
- **Never** recompute old ledger rows from today’s config.

`execution_id` default convention (existing): `ec_{event_id}` for the primary role row; if multiple roles per event are needed, use `ec_{event_id}_{execution_role}`.

### 7.4 Reconstruction vs materialization

1. Replay events in timestamp/`event_id` order → rebuild quantities/lifecycle.
2. Sum ledger exit nets → reconstructed net PnL; sum fees/slip/spread → costs.
3. Compare to `simulated_trades` materialized fields and optional trade cost summary.

**Default reconciliation mode: read-only audit.**  
Mismatch → emit integrity warning / report; **do not** auto-repair in Phase 6.0.x unless an explicit repair tool is later approved.

Preserve simulator ambiguity policy `conservative_stop_first` in rebuild (same event ordering / reason fields).

## 8. JSONB financial serialization & hashing

1. All Decimal/money values in JSONB → **decimal strings** (no binary floats), consistent with `LedgerEntry.public_dict()`.
2. Fields used for filter/sort/compare also exist as typed `NUMERIC(p,s)` columns.
3. **Never** `DOUBLE PRECISION` / `REAL` for persisted financial amounts.
4. Canonical JSON for hashing:
   - UTF-8
   - Object keys sorted lexicographically at every level
   - No insignificant whitespace
   - Decimals as normalized strings (fixed scale or `format(v, 'f')` without scientific notation)
   - Timestamps as ISO-8601 UTC with `Z` or explicit offset
5. `content_hash` / `payload_hash` = lowercase hex SHA-256 of canonical bytes.

## 9. AI optional design

- No required AI tables.
- Optional future `ai_explanation_records` nullable FK to snapshots; never blocks persistence.
- Do not persist vision image bytes by default.

## 10. Users / auth

**No `users` table.** Journal is instance-local until a later identity phase.

## 11. Related docs

- Schema: `PHASE_6_0_1_DATABASE_SCHEMA.md`
- ER: `PHASE_6_0_1_ENTITY_RELATIONSHIPS.md`
- API: `PHASE_6_0_1_API_DESIGN.md`
- Migration / tests: `PHASE_6_0_1_MIGRATION_PLAN.md`
