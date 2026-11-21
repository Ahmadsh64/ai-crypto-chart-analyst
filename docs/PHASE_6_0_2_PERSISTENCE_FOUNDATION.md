# Phase 6.0.2 — Supabase PostgreSQL Persistence Foundation

**Status:** Implemented  
**Provider:** Supabase (managed PostgreSQL)  
**Scope:** Async DB infrastructure, Alembic migrations 1–3, identity helpers, initial ORM + atomic analysis persist.  
**Out of scope:** Supabase Auth / Storage / Realtime; Phase 6.0.3 history APIs; trading formula changes.

## 1. What landed

| Item | Location |
|------|----------|
| Feature flag (default **off**) | `PERSISTENCE_ENABLED` / `Settings.persistence_enabled` |
| Async SQLAlchemy 2.x + asyncpg | `backend/app/db/session.py` |
| ORM: `analysis_sessions`, `analysis_snapshots`, `decisions`, `trade_plans` | `backend/app/db/models/analysis.py` |
| Deterministic IDs + payload_hash | `backend/app/db/identity.py` |
| Decimal-safe JSONB codec | `backend/app/db/json_codec.py` |
| Consistency classifier | `backend/app/db/consistency.py` |
| Atomic snapshot+decision+plan TX | `backend/app/db/repositories/analysis.py` |
| Alembic revisions 1–3 | `backend/alembic/versions/` |
| Health component | `GET /api/v1/health` → `database` |
| Unit tests (local/mocked) | `backend/tests/test_db_phase_6_0_2.py` |
| Live Supabase tests | `backend/tests/test_db_supabase_live.py` |

## 2. Environment (server-only — never frontend)

See `.env.example`:

- `PERSISTENCE_ENABLED=false` (default)
- `DATABASE_URL=postgresql+asyncpg://…`
- Optional: `SUPABASE_DB_URL`, `SUPABASE_DB_HOST`, `SUPABASE_DB_PASSWORD`, pool settings
- `SUPABASE_SSL_CA_FILE` — path to official Supabase Root CA PEM (`prod-ca-2021.crt`). Relative paths resolve from `backend/` (not cwd). Supabase connections use `ssl.SSLContext` with `CERT_REQUIRED` + hostname verification (never `ssl=True` / `CERT_NONE`).
- Alembic (`alembic/env.py`) reuses the same URL + verifying SSLContext via `alembic_database_url` / `alembic_async_connect_args` (Phase 6.0.2.1).

Credentials must not be committed or exposed via `NEXT_PUBLIC_*`.

## 3. Apply migrations (when credentials configured)

```bash
cd backend
# set PERSISTENCE_ENABLED / DATABASE_URL or SUPABASE_DB_URL in .env
alembic upgrade head
```

Revisions:

1. `0001_extensions` — `pgcrypto`
2. `0002_analysis_core` — sessions + snapshots (`analysis_run_id`, NUMERIC precision, consistency check)
3. `0003_decisions_trade_plans` — extracts with `ON DELETE RESTRICT` + `analysis_run_id` unique

## 4. Runtime behavior

- Persistence **off** → app runs normally; health `database` = ok / “Persistence disabled”.
- Persistence **on** but DB down → app still serves analysis; health `database` unavailable → overall **degraded**.
- `persist_analysis_bundle` is available for Phase 6.0.3 orchestration; live Analyze routes are **not** auto-persisting yet.

## 5. Identity helpers

- `new_analysis_run_id()` → `ar_…`
- `new_replay_session_id()` / `stable_replay_session_id(…)`
- `deterministic_trade_id` / `deterministic_event_id` / `deterministic_execution_id`
- `compute_payload_hash` + conflict policy (`idempotent` vs `conflict`)

Simulator `lifecycle` / `TradeSimulator` now prefer deterministic IDs when context is present. Fill/ambiguity math unchanged.

## 6. Test distinction

| Suite | Purpose |
|-------|---------|
| `test_db_phase_6_0_2.py` | Always-run unit tests (no network) |
| `test_db_supabase_live.py` | **LIVE** only when `PERSISTENCE_ENABLED=true` + real URL; skipped otherwise → report **NOT VERIFIED** |

Local Postgres live runs require `ALLOW_LOCAL_DB_LIVE_TEST=true`.

## 7. Explicit non-goals (stop here)

- No Phase 6.0.3 history REST routes
- No replay/sim/cost table migrations (4–11)
- No Supabase Auth, Storage, or Realtime
- No changes to Entry/SL/TP/RR/sizing/LONG/SHORT/WAIT/NO TRADE formulas
