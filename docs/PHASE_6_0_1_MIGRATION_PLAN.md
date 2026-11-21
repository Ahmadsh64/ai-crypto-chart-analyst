# Phase 6.0.1 — Migration Plan (toward 6.0.2+)

Phase 6.0.1 / **6.0.1.1** creates **no** Alembic revisions and installs **no** database.

## 1. Preconditions (already in repo)

| Item | Status |
|------|--------|
| `DATABASE_URL` in `Settings` | Present |
| sqlalchemy / asyncpg / alembic | In `requirements.txt`, unwired |
| Deterministic sim event IDs | **Not present** (random today) — required before durable rebuild |
| User auth | Absent — no users migration |

## 2. Migration order (Alembic revisions)

| Order | Theme | Objects |
|------:|-------|---------|
| 1 | Extensions | `pgcrypto` |
| 2 | Live analysis core | `analysis_sessions`, `analysis_snapshots` (**include `analysis_run_id`, consistency columns**) |
| 3 | Decision / plan extracts | `decisions`, `trade_plans` (**`analysis_run_id` UK**) |
| 4 | Replay sessions | `replay_sessions` |
| 5 | Historical analysis | `historical_analysis_snapshots` |
| 6 | Simulation | `simulated_trades` + `UNIQUE(trade_id, replay_session_id)` |
| 7 | Trade events | `trade_events` + logical UNIQUE + `UNIQUE(trade_id, event_id)` + FK to trades |
| 8 | Costs | `execution_cost_ledger` + composite FKs to events/trades + `UNIQUE(trade_id, source_event_id, execution_role)` + explicit `NUMERIC(p,s)` |
| 9 | Reports | `backtest_reports` |
| 10 | Journal | `trade_journal_entries` RESTRICT |
| 11 | Index polish | consistency/status/time indexes |

Expand-only initially. Compatibility note: if an early draft migration omitted `analysis_run_id` or composite FKs, add **follow-up expand revisions** — never silently rewrite historical financial rows.

## 3. Implementation sequence

### Phase 6.0.2 — Persistence foundation ✅
1. Async SQLAlchemy engine/session + feature flag. ✅
2. ORM models matching refined schema. ✅
3. Migrations 1–3. ✅
4. Health: database component. ✅
5. Introduce **deterministic ID helpers** for persistence path (and plan engine alignment) without changing fill/ambiguity math. ✅  
   Details: `docs/PHASE_6_0_2_PERSISTENCE_FOUNDATION.md`

### Phase 6.0.3 — Analysis history
1. Orchestration generates `analysis_run_id`.
2. Atomic TX persist snapshot+decision+plan.
3. Consistency classifier (ALIGNED / DIVERGED / …).
4. History APIs including `by-run`.

### Phase 6.0.4 — Replay session persistence
1. Checkpoint sessions.
2. Dual-read strategy.
3. Selective historical analysis persistence.

### Phase 6.0.5 — Simulation + costs durability
1. Deterministic `trade_id` / `event_id` / `execution_id`.
2. Idempotent event+ledger TX with conflict on payload mismatch.
3. Read-only reconstruction audit API.
4. RESTRICT delete proofs.

### Phase 6.0.6 — Reports + Journal
1. Store reports.
2. Journal CRUD (metadata only).

## 4. Future test plan (required)

### 4.1 Event idempotency
- Duplicate identical event → single row, no double quantity apply.
- Duplicate event_id with changed **price** → conflict, no overwrite.
- Duplicate event_id with changed **quantity** → conflict, no overwrite.
- Replay restart resumes without duplicating TP/SL/partial exits.
- Replay reset + deterministic rebuild reproduces same event_ids and payload hashes.
- Concurrent duplicate insertion → one winner, no double apply (TX + unique constraints).

### 4.2 Analysis run / consistency
- One `analysis_run_id` on snapshot+decision+plan.
- Shared run id with divergent timestamps/levels → `DUAL_FETCH_DIVERGED`, both payloads preserved.
- ALIGNED only when §alignment checks pass.
- Atomic TX: failure mid-write leaves no orphan extracts.
- Re-POST same run+hash → idempotent; same run+different hash → 409.

### 4.3 Financial reconstruction
- Full entry + full exit.
- Multiple partial exits.
- TP1 then TP2 then final exit.
- Stop-loss exit (including conservative_stop_first ambiguity path).
- Entry expiry without fill (no ledger fill / no false PnL).
- Fee allocation across partial exits (`allocate_entry_fee` semantics).
- LONG and SHORT gross/net PnL.
- Quantity conservation identity.
- Ledger reconstruction vs materialized `simulated_trades` (audit diffs).
- Deterministic replay rebuild equality.
- Old ledger unchanged when fee config later changes.

### 4.4 Ledger FK / precision
- Insert ledger with wrong `trade_id` for `source_event_id` → FK failure.
- Insert ledger with mismatched `replay_session_id` → FK failure.
- Two roles same event allowed; duplicate same role → unique violation / idempotent.
- NUMERIC(28,12) / (18,10) round-trip without float drift.
- JSONB decimal strings + deterministic content_hash stability across key order.

### 4.5 Delete integrity
- Delete journal → trade/events/ledger remain.
- Attempt delete trade with events → RESTRICT.
- Attempt delete event with ledger → RESTRICT.

## 5. Replay volume / pooling / backup

Unchanged recommendations: do not persist every candle; batch event TX; pool_size≈5; nightly `pg_dump`.

## 6. Risks and tradeoffs

| Risk | Mitigation |
|------|------------|
| Random runtime IDs today | Deterministic helpers before durable rebuild claims |
| Claiming ALIGNED via run id alone | Explicit multi-field classifier |
| Silent event overwrite | payload_hash conflict policy |
| Auto-repair hiding bugs | Read-only reconstruction audit default |
| Float in JSONB | Decimal strings + typed columns |
| Cascade deletes | RESTRICT everywhere on financial graph |

## 7. Unresolved questions

1. Auto-persist Analyze vs explicit Save?
2. Retention TTL for live snapshots?
3. When to migrate in-memory simulator ID generation vs adapter-only mapping?
4. Max report JSONB size / object storage?
5. Future nullable `owner_id`?

## 8. Success criteria before persistence “on”

- Migrations apply on empty DB.
- Live analysis works with DB down.
- Idempotency + conflict tests green.
- Reconstruction audit tests green.
- No trading formula changes.
- Design docs 6.0.1.1 requirements covered.
