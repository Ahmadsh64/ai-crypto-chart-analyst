# Phase 0.1 — Migration & Dependency Validation

**Mode:** Read-only audit  
**Date:** 2026-11-20  
**Follows:** Phase 0 preservation + Deployment Readiness Review 2  
**Scope:** Alembic `0001`–`0004`, backend dependency pins, Supabase compatibility (no live DB)

### Safety compliance

| Rule | Status |
|------|--------|
| No source / requirements / migration edits | Met |
| No package install/uninstall | Met |
| No migration execution / DB connections | Met |
| No stage / commit / push / deploy | Met |
| Only new file: this report | Met |

---

## 1. Migration dependency graph

```text
(None)
  │
  ▼
0001_extensions
  │  CREATE EXTENSION IF NOT EXISTS "pgcrypto"
  ▼
0002_analysis_core
  │  analysis_sessions
  │  analysis_snapshots  (FK → sessions ON DELETE SET NULL)
  ▼
0003_decisions_trade_plans
  │  decisions     (FK → snapshots ON DELETE RESTRICT, UK analysis_run_id)
  │  trade_plans   (FK → snapshots ON DELETE RESTRICT, UK analysis_run_id)
  ▼
0004_scanner_persistence          ← current local HEAD
     scanner_runs
     market_opportunities  (FK → scanner_runs.id ON DELETE SET NULL)
     [no FKs into 0002/0003 analysis tables]
```

| Revision ID | `down_revision` | Chain status |
|-------------|-----------------|--------------|
| `0001_extensions` | `None` | Root — OK |
| `0002_analysis_core` | `0001_extensions` | OK |
| `0003_decisions_trade_plans` | `0002_analysis_core` | OK |
| `0004_scanner_persistence` | `0003_decisions_trade_plans` | OK — linear, no branches |

**Alembic head (local):** `0004_scanner_persistence`

---

## 2. Detailed migration findings

### 2.1 `0001_extensions`

| Check | Finding |
|-------|---------|
| Upgrade | `CREATE EXTENSION IF NOT EXISTS "pgcrypto"` — needed for `gen_random_uuid()` on some PG builds |
| Downgrade | Intentional no-op (does not drop extension) — safe on shared Supabase |
| Idempotency | Extension create is idempotent; Alembic version table still required for overall safety |
| Empty DB | Compatible |
| Data loss | None |
| PG / Supabase | Compatible; `pgcrypto` typically available on Supabase Postgres |

**Verdict:** Accept for empty Supabase apply.

### 2.2 `0002_analysis_core`

| Check | Finding |
|-------|---------|
| Tables | `analysis_sessions`, `analysis_snapshots` |
| PK | UUID + `gen_random_uuid()` server default |
| FK | `analysis_snapshots.analysis_session_id` → `analysis_sessions.id` **ON DELETE SET NULL** |
| Unique | `analysis_run_id`; `(snapshot_kind, content_hash)` |
| Check | `consistency_status` enum-like IN-list |
| Indexes | Market/time DESC expression indexes via `sa.text("… DESC")` — PostgreSQL-compatible |
| Types | `NUMERIC(28,12)`, `JSONB`, `TIMESTAMPTZ` — Supabase-ready |
| Downgrade | Drops indexes then tables — **destructive** (expected for downgrade) |
| Idempotency | Plain `create_table` — **not** re-runnable without Alembic bookkeeping |
| Empty DB | Compatible (create-only) |
| Data loss on upgrade | None (additive) |

**Verdict:** Accept. Apply once via Alembic only.

### 2.3 `0003_decisions_trade_plans`

| Check | Finding |
|-------|---------|
| Tables | `decisions`, `trade_plans` |
| FK | Both → `analysis_snapshots.id` **ON DELETE RESTRICT** (preserves financial extracts) |
| Unique | `analysis_run_id` per table |
| Partial unique indexes | `decision_id` / `plan_id` where NOT NULL — PostgreSQL partial unique OK |
| Downgrade | Drops indexes/tables — destructive |
| Empty DB | Compatible after `0002` |
| Data loss on upgrade | None (additive) |

**Verdict:** Accept. Aligns with Phase 6.0.3 soft-persist / History design.

### 2.4 `0004_scanner_persistence` (special attention)

| Check | Finding |
|-------|---------|
| Stated intent | Additive; **does not** alter `analysis_sessions` / snapshots / decisions / trade_plans |
| Tables | `scanner_runs`, `market_opportunities` |
| FK | `market_opportunities.last_scan_run_id` → `scanner_runs.id` **ON DELETE SET NULL** only |
| Cross-domain FKs to analysis tables | **None** — isolation preserved |
| Unique | `scan_id`; `opportunity_id`; `(slot_key, setup_generation)`; partial unique **one open row per `slot_key`** |
| Checks | status / decision / direction IN-lists |
| Indexes | Lookup, status/eval, actionable (partial), last_scan |
| Downgrade | Drops opportunity + run tables — **scanner durable history lost** |
| Empty DB | Compatible after `0001`–`0003` |
| Data loss on upgrade | None (additive DDL) |

#### Durable scanner persistence vs in-memory `OpportunityStore`

| Layer | Role today |
|-------|------------|
| `OpportunityStore` (in-memory) | **Authoritative for live API** — `GET /opportunities*` reads this store |
| `persist_scan_bundle` (`app/db/repositories/scanner.py`) | **Soft-fail durable mirror** after a scan finishes; gated by `PERSISTENCE_ENABLED` |
| `MarketOpportunityScanner.run_scan` | Updates memory first; then attempts DB persist; failures logged — **scan still succeeds** |

**Conflict assessment:** **No behavioral conflict.**  
`0004` enables optional durability; it does **not** replace the process-local store or the process-local overlap lock. Without `0004` applied, soft-persist fails (missing tables) while in-memory Opportunities continue. With `0004` + persistence on, DB retains runs/opportunities across restarts, but **API still serves memory** until/unless a future hydrate path is added (not required for this audit).

**ORM alignment:** `app/db/models/scanner.py` maps to the same table/constraint names; `alembic/env.py` imports `ScannerRun` / `MarketOpportunityRow`.

---

## 3. Migration `0004` decision recommendation

| Option | Recommendation |
|--------|----------------|
| Include `0004` in release commit | **YES — recommend include** |
| Apply `0004` on empty Supabase after `0001`–`0003` | **YES — if scanner soft-persist should work in prod** |
| Apply only through `0003` | Acceptable only if accepting soft-fail of scanner DB writes |
| Treat `0004` as conflicting with in-memory scanner | **No** — complementary dual-write |

**Recommended decision:** Approve `0004_scanner_persistence` as the Alembic **head** for the controlled release, document that Opportunities UI remains memory-backed at runtime, and apply `alembic upgrade head` (through `0004`) in a later approved migration window.

**Not recommended:** Skipping `0004` while shipping code that calls `persist_scan_bundle` (creates noisy soft-failures / incomplete durability).

---

## 4. Dependency compatibility matrix

### 4.1 Requirements sources

| File | Present? |
|------|----------|
| `backend/requirements.txt` | **Yes** — sole dependency lockfile for API |
| Root `requirements.txt` | **No** |
| `infra/docker/Dockerfile.api` | `FROM python:3.12-slim`; `pip install -r requirements.txt` |
| `runtime.txt` / `.python-version` | **Absent** |

Declared target: comment `# Python 3.12+` · Docker/Render intent: **3.12** · Local observed earlier: **3.13.1**

### 4.2 Key pins (as written — not installed this phase)

| Package | Pin | Role | Python 3.12 notes |
|---------|-----|------|-------------------|
| `fastapi` | `0.115.6` | API | OK with 3.12 |
| `uvicorn[standard]` | `0.34.0` | ASGI | OK |
| `sqlalchemy` | `2.0.36` | ORM / Alembic | OK with asyncpg |
| `alembic` | `1.14.0` | Migrations | Uses async engine in `env.py` |
| `asyncpg` | `0.30.0` | DB driver | Required for app + Alembic online |
| `greenlet` | `>=3.1.1` | SQLAlchemy async | OK |
| `psycopg2-binary` | `2.9.10` | Listed | **Not required** by current async Alembic path; unused by app imports (optional dead weight) |
| `pandas` | `2.2.3` | Quant/market | OK on 3.12 |
| `numpy` | `2.2.1` | With pandas 2.2.3 | Compatible pair |
| `pandas-ta` | `0.3.14b` | Listed | **BLOCKED** — not on current PyPI; **unused** by `backend/app` |
| `openai` / `httpx` / `websockets` / `pillow` / … | pinned | Runtime | Assumed OK on 3.12; not re-tested here |

### 4.3 `pandas-ta` vs `pandas` / `numpy`

| Scenario | Outcome |
|----------|---------|
| Keep `pandas-ta==0.3.14b` | Install fails (Evidence from Review 2 dry-run) |
| Replace with `0.4.71b0` without retune | Dry-run pulled **pandas 3.x** + numba — **conflicts** with `pandas==2.2.3` / `numpy==2.2.1` |
| Remove unused `pandas-ta` | Matches code; unblocks `pip install` — **recommended future change** |

### 4.4 Exact dependency set required for Python 3.12 (logical)

**Must install for production API + migrations (conceptually):**

- Web: `fastapi`, `uvicorn[standard]`, `python-multipart`
- Settings: `pydantic`, `pydantic-settings`, `email-validator`, `python-dotenv`
- DB: `sqlalchemy==2.0.36`, `alembic==1.14.0`, `asyncpg==0.30.0`, `greenlet>=3.1.1`
- Market: `ccxt`, `pandas==2.2.3`, `numpy==2.2.1` (**without** broken `pandas-ta` pin)
- HTTP/WS/AI/utils: as pinned (`httpx`, `aiohttp`, `websockets`, `openai`, `orjson`, `pillow`, `reportlab`, optional `redis`)

**Dev/test-only (omit from slim prod image if desired later):** `pytest*`, `respx`, `ruff`

**This phase does not modify pins.**

---

## 5. Supabase compatibility findings

| Topic | Assessment |
|-------|------------|
| Extension | `pgcrypto` via `0001` (`IF NOT EXISTS`) — OK for empty project |
| Types | UUID, JSONB, NUMERIC, TIMESTAMPTZ, partial indexes — native PG |
| asyncpg | App + Alembic online path; `NullPool` for migrations |
| SSL | Verifying CA via `ssl_config` / `SUPABASE_SSL_CA_FILE` / `prod-ca-2021.crt` (packaging still a release concern) |
| Session Pooler | Prefer **Session** mode URL for long-lived asyncpg + Alembic; Transaction pooler can break prepared statements |
| Migration execution | Manual `alembic upgrade head` from `backend/` with env loaded — **not** auto on boot (good) |
| Empty DB apply order | `0001` → `0002` → `0003` → `0004` |
| Concurrent app writes during first migrate | Prefer offline/maintenance window; upgrades are create-only so lower risk than alters |
| Production connection this audit | **Not performed** |

---

## 6. Remaining blockers

1. **`pandas-ta==0.3.14b`** still blocks reproducible Render/Docker `pip install`.  
2. No `runtime.txt` / `.python-version` — Render may not pin 3.12 unless set in dashboard.  
3. CA cert still not on `origin/main` (packaging; outside this migration edit).  
4. Working tree still uncommitted — migrations not on GitHub yet.  
5. If prod ships scanner soft-persist without applying `0004`, DB writes soft-fail (non-fatal but incomplete).  
6. Downgrade of any revision is data-destructive — ops must not “fix” issues with downgrade on prod.

---

## 7. Recommended remediation order (future approved phases)

1. **Dependency:** remove unused `pandas-ta` line (or replace only after a proven 3.12 matrix) — edit `backend/requirements.txt` only when approved.  
2. **Pin runtime:** document/set Render + Docker to **Python 3.12** (`runtime.txt` or dashboard).  
3. **Release commit:** include migrations `0001`–`0004` + CA + app code (per Phase 0 manifest).  
4. **Supabase (approved window):** backup/PITR check → `alembic upgrade head` on empty or known-empty schema.  
5. **Verify:** health `database=ok`; scanner soft-persist succeeds when `PERSISTENCE_ENABLED=true`.  
6. **Do not** introduce a second scanner or change scheduling as part of dependency fixes.

---

## 8. Explicit files that may require future modification

| File | Why (future only) |
|------|-------------------|
| `backend/requirements.txt` | Remove/fix `pandas-ta`; optionally drop unused `psycopg2-binary` |
| `infra/docker/Dockerfile.api` | Already 3.12; start command may need `$PORT` for Render |
| New `backend/runtime.txt` or `.python-version` | Pin 3.12 for PaaS (does not exist today) |
| `backend/alembic/versions/*` | **Do not edit** existing revisions; only add new revisions if schema evolves |
| `backend/app/db/ssl_config.py` / CA path packaging | Deploy artifact presence |
| `backend/app/main.py` | Future docs disable / auth gates (separate security approval) |

**Do not modify in this phase:** trading engines, scanner interval/lock logic, migration bodies `0001`–`0004`, or live DB state.

---

## 9. Completion checklist

| Criterion | Status |
|-----------|--------|
| All four migrations reviewed | **PASS** |
| Dependency conflicts identified | **PASS** (`pandas-ta` primary) |
| Only this audit report added | **PASS** |
| No DB operations | **PASS** |
| No Git staging/commits | **PASS** |
| No deployment | **PASS** |

### Phase 0.1 result

- Migration chain **linear and sound** through **`0004`**.  
- **`0004` recommended for inclusion** — durable scanner tables, soft-persist complement to in-memory store, **no conflict**.  
- Dependency set for Python **3.12** is otherwise coherent **except** the broken unused `pandas-ta` pin.

**STOP.** Awaiting explicit approval before any remediation edits, commits, or migration execution.
