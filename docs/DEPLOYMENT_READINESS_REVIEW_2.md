# Deployment Readiness Review 2 — Clarification Audit

**Mode:** Read-only (no code, config, dependency, migration, Git, or deploy changes)  
**Date:** 2026-11-20  
**Inputs:** Accepted verdict from `docs/DEPLOYMENT_READINESS_AUDIT.md` + six clarification questions  
**Production deploy approval:** **Not granted** (this review does not request or perform deploy)

---

## Executive summary

| Question | Short answer |
|----------|----------------|
| 1. Missing Phase 5.5 / 6.0.x vs `origin/main` | **Not missing commits** — `HEAD` == `origin/main` (`899d48a`). Feature work is **uncommitted / untracked** in the working tree. |
| 2. `pandas-ta==0.3.14b` on Render | **Cannot install** on current PyPI for the tested interpreter; package is also **unused** by app code. |
| 3. Supabase CA / SSL | Verifying `SSLContext` + `prod-ca-2021.crt`; CA file **not on GitHub**; duplicate local copy exists. |
| 4. Protect Render API (not CORS) | CORS is not auth. Need edge auth, private networking/BFF, IP allowlist (plan-limited), and/or app gates; `/docs` always on today. |
| 5. Single-instance scanner | Safe against **concurrent** scans **inside one process**; restarts wipe in-memory state; multi-instance still unsafe. |
| 6. Extra prod risks | Uncommitted deploy tree, install pin, migration ops, in-memory loss, open scan/docs, pooler/TLS mistakes. |

**Final production readiness verdict:** **NOT READY**

---

## 1. Findings

### 1.1 Git: what is missing from `origin/main`

**Finding:** There are **zero local commits ahead of** `origin/main`. The gap is a **dirty working tree**, not unpublished commits.

**Evidence:**

```text
git rev-list --left-right --count origin/main...HEAD  →  0  0
HEAD / origin/main tip: 899d48a Merge remote GitHub README with local project history.
```

**What `origin/main` does contain (design only for 6.0.1):** Phase 6.0.1 docs (`PHASE_6_0_1_*`), Phase 5.1–5.4 docs/tests through AI orchestration design artifacts. **No** `backend/app/scanner/`, **no** `backend/app/db/`, **no** Alembic tree, **no** history/opportunities routes/pages.

**Untracked implementation trees (local only; sample counts):**

| Area | Approx. untracked paths | Role |
|------|-------------------------|------|
| `backend/app/scanner/` | 11 files | Phase 5.5 scheduler + universe/analyze |
| `backend/app/db/` | 13 files | Phase 6.0.2 session/SSL/ORM/repos |
| `backend/alembic*` | 6 paths | Migrations `0001`–`0003` + `alembic.ini` |
| History / opportunities API | `history.py`, `opportunities.py` + schemas | Phase 6.0.3.1 / 5.5 HTTP |
| `analysis_persistence_service.py` | 1 | Phase 6.0.3 soft-persist |
| Frontend History / Opportunities | pages + components + libs (untracked) | UI |
| Docs | `PHASE_5_5_*`, `PHASE_6_0_2_*`, `PHASE_6_0_3_*`, audit docs | Specs |
| `backend/prod-ca-2021.crt` (+ duplicate `prod-ca-2021 (1).crt`) | CA PEM | Supabase TLS |
| `frontend/vercel.json` | Vercel hints | Deploy metadata |
| Related tests | `test_phase_5_5_*`, `test_db_*`, `test_phase_6_0_3_*`, … | QA |

**Tracked but modified wiring** (also required for those features to boot): includes at least:

- `backend/app/main.py` (scanner lifespan, history/opportunities routers, docs always on)
- `backend/app/core/config.py` (persistence/Supabase/CORS/OpenAI settings)
- `backend/requirements.txt` (SQLAlchemy/asyncpg/alembic + `pandas-ta` pin)
- `frontend/lib/navigation.ts`, `frontend/services/api.ts`, `frontend/types/api.ts`
- `frontend/app/(app)/chart-analyzer/page.tsx` and related UI files
- `.env.example`, `.gitignore`, `README.md`

**Spot-check (`git cat-file` against `origin/main`):** all of the following are **MISSING_ORIGIN**:

- `backend/app/scanner/service.py`
- `backend/app/db/session.py`
- `backend/alembic/versions/0003_decisions_trade_plans.py`
- `backend/app/api/routes/history.py`
- `backend/app/api/routes/opportunities.py`
- `frontend/app/(app)/history/page.tsx`
- `frontend/app/(app)/market-opportunities/page.tsx`
- `docs/PHASE_5_5_IMPLEMENTATION_PLAN.md`
- `docs/PHASE_6_0_2_PERSISTENCE_FOUNDATION.md`
- `docs/PHASE_6_0_3_ANALYSIS_PERSISTENCE.md`
- `backend/prod-ca-2021.crt`
- `frontend/vercel.json`

**Classification:** **BLOCKED** for any GitHub → Vercel/Render deploy of the current Analyzer.

---

### 1.2 `pandas-ta==0.3.14b` vs intended Render Python

**Intended Render environment (from repo artifacts):**

- `infra/docker/Dockerfile.api` → `python:3.12-slim`
- Local venv observed: **Python 3.13.1**
- No `runtime.txt` / `.python-version` in repo

**Evidence (read-only dry-run on local 3.13.1 venv):**

```text
pip install pandas-ta==0.3.14b --dry-run
→ ERROR: No matching distribution found for pandas-ta==0.3.14b
→ available versions reported: 0.4.67b0, 0.4.71b0
```

```text
pip install pandas-ta==0.4.71b0 --dry-run
→ Would install: pandas-ta-0.4.71b0, numba, llvmlite, numpy-2.2.6, pandas-3.1.1
```

**App usage:** Grep over `backend/app/**/*.py` and `backend/tests/**/*.py` found **no** `pandas_ta` / `pandas-ta` imports. Indicators appear implemented without this package.

**Conflict:** Root `requirements.txt` pins `pandas==2.2.3`, while `pandas-ta==0.4.71b0` dry-run resolves to **pandas ≥ 2.3.2** (would pull pandas 3.x) — incompatible with current pins without a coordinated upgrade.

**Classification:**

| Option | Result | Class |
|--------|--------|-------|
| Keep `pandas-ta==0.3.14b` | Install fails on current PyPI index | **BLOCKED** |
| Upgrade to `0.4.71b0` without retuning pandas/numpy | Dependency conflict risk | **BLOCKED** until tested on Python 3.12 |
| Remove unused `pandas-ta` (recommended remediation later) | Matches actual code usage | Recommended (needs future approved change) |

**Tested compatible alternative (evidence-based):** There is **no** currently tested pin that both (a) installs cleanly and (b) preserves `pandas==2.2.3`. The **safest** remediation path is **omit unused `pandas-ta`**, not chase a newer beta. If TA helpers are needed later, evaluate on **Python 3.12** in an isolated install matrix after approval.

---

### 1.3 Supabase PostgreSQL CA / SSL verification

**How the code behaves (local tree):**

1. For URLs matching Supabase hosts (`supabase.com` / `supabase.co`), `ssl_connect_arg_for_url` **requires** a CA and builds `ssl.create_default_context(cafile=…)`.
2. Context is asserted: `verify_mode == CERT_REQUIRED`, `check_hostname == True`.
3. Never uses `ssl=True` alone or `CERT_NONE`.
4. Path resolution: `SUPABASE_SSL_CA_FILE` absolute as-is; relative paths from **backend package root**; empty → default `backend/prod-ca-2021.crt` if present.
5. Same helpers used by runtime engine (`app.db.session`) and Alembic (`alembic_async_connect_args`).
6. Errors sanitized (URLs/passwords stripped) before logs/health text.

**Local CA evidence:**

- `backend/prod-ca-2021.crt` exists; PEM header `BEGIN CERTIFICATE` verified (public CA material).
- Duplicate `backend/prod-ca-2021 (1).crt` also present — should **not** be treated as the canonical deploy artifact.
- `git ls-files backend/prod-ca-2021.crt` empty → **not on remote**.

**Ops implications:**

- Render Root Directory `backend` + committed `prod-ca-2021.crt` **or** explicit `SUPABASE_SSL_CA_FILE` pointing at a mounted secret file.
- Use Session Pooler URL consistent with long-lived asyncpg clients; wrong pool mode/host can fail TLS or prepared statements.
- Missing CA with `PERSISTENCE_ENABLED=true` → SSL configuration failure / DB unavailable (app may still serve analysis soft-fail paths).

**Classification:** Design **READY**; packaging on GitHub **BLOCKED**.

---

### 1.4 Protecting the Render API directly (not CORS)

**Finding:** CORS only constrains **browser** cross-origin calls. It does **not** authenticate curl, scripts, OpenAPI explorers, or non-browser clients. Current app has **no** enforced API authentication on routes.

**Evidence:**

- `CORSMiddleware` with `CORS_ORIGINS` in `main.py`.
- `FastAPI(..., docs_url="/docs", redoc_url="/redoc")` — always enabled; default `/openapi.json` remains exposed.
- `POST /api/v1/opportunities/scan` has **no** `Depends`/API-key check (`opportunities.py`).
- `verify_optional_api_key` in `security.py` is **unused**; Settings has **no** `app_api_key` field — stub cannot work as written.

**Practical protection options (ops / future approved changes):**

| Mechanism | Protects `/docs`, `/openapi.json`, `/scan`? | Notes | Class |
|-----------|-----------------------------------------------|-------|-------|
| **Cloudflare Access / Zero Trust** (or similar IdP) in front of Render hostname | Yes, at edge before app | Works with browser SPA if policies allow; strong for private beta | REQUIRES USER DECISION |
| **Render Private Service** | Public internet blocked | Browser on Vercel **cannot** call API directly; needs Next.js BFF/proxy on Vercel private network — architecture change | REQUIRES USER DECISION |
| **Render Inbound IP Rules** | Yes, network layer | Documented for **Scale/Enterprise** web services; poor fit for Vercel’s dynamic egress + end-user browsers | REQUIRES USER DECISION |
| **Office/VPN IP allowlist only** | Yes for operators | Breaks normal remote users unless all traffic exits that IP | REQUIRES USER DECISION |
| **Application shared secret / API key middleware** | Yes, if applied to docs + routes | Needs Settings field + wiring; still not end-user auth | REQUIRES USER DECISION (no auth without approval) |
| **Disable docs/OpenAPI in production** | Docs/schema only | Code/config change later; does not protect `/scan` alone | REQUIRES USER DECISION |
| **Vercel Deployment Protection alone** | UI only | Does **not** protect Render URL | Insufficient alone |
| **CORS-only** | No | Not authentication | Reject as control |

**Recommended private-beta pattern (decision, not implementation):** Edge access control on the **Render hostname** (Cloudflare Access or equivalent) **plus** keep instance count at 1; treat Vercel protection as UI-only complement. Do not claim CORS secures `/scan` or `/docs`.

**Classification:** Open API surface **BLOCKED** for “private production” until a non-CORS control is chosen and applied.

---

### 1.5 Single-instance scanner: duplicates and restarts

**Architecture (local tree):**

- Scanner starts inside FastAPI `lifespan` (`get_scanner().start()`).
- Loop every `scan_interval_seconds` (default **300**).
- Overlap control: process-local `asyncio.Lock` in `MarketOpportunityScanner`.
- Results: in-memory `OpportunityStore` (not Postgres).
- Singleton via module-global `_scanner`.

**Duplicate execution:**

| Scenario | Behavior | Safe? |
|----------|----------|-------|
| One Web Service instance, one process | Lock serializes scans; callers while locked get `skipped` | **Yes** (concurrent) |
| Manual `POST /scan` during scheduled scan | Second call skipped if lock held; if both arrive unlocked, they **queue serially** (two full scans back-to-back possible) | Acceptable / not parallel |
| Two Render instances | Two locks, two stores, two loops → **duplicate exchange load** + inconsistent reads | **No** |
| Background Worker + Web both scanning | Second scheduler | **No** (explicitly forbidden) |

**Restarts / crashes:**

| Event | Effect |
|-------|--------|
| Process kill mid-scan | In-flight results discarded; no durable scan checkpoint |
| Clean shutdown | `stop()` cancels task; store state not persisted |
| Boot | New empty store; loop starts; first scan runs (can be heavy) |
| After restart | Opportunities UI empty until scan completes — **expected data loss of scanner RAM state**, not of Supabase History rows |

**Classification:** Single always-on instance **READY** for “no concurrent duplicate scans in-process.” Not resilient to horizontal scale. Restart behavior is **safe against double-writers to DB for opportunities** (opportunities are not DB-backed) but **loses** opportunity cache.

---

### 1.6 Additional production risks (data loss, duplicates, migrations)

| Risk | Evidence / mechanism | Impact |
|------|----------------------|--------|
| Deploying stale GitHub `main` | Untracked Phase 5.5/6.0.x | Wrong product / missing History & Opportunities |
| `pip install` failure | `pandas-ta==0.3.14b` | Render build fails |
| Missing CA on disk | Untracked `prod-ca-2021.crt` | Persistence/TLS fail; health degraded |
| Alembic not applied / applied twice incorrectly | Manual `alembic upgrade head`; head `0003_decisions_trade_plans` | Empty schema or operator error |
| Migrating with wrong URL (direct vs pooler, password, SSL) | Same Settings URL for app + Alembic | Migration connection failure |
| Migrating while app writes | Soft-persist Analyze + unique `analysis_run_id` | Prefer maintenance window; conflicts handled as idempotent/conflict in app layer but DDL still risky |
| Auto-migrate on boot absent | By design | Good; forgetting manual migrate → History broken |
| Free-tier sleep / multi-instance | Platform ops | WS drops; scanner gaps or duplicates |
| Unauthenticated `/scan` + OpenAI uploads | Open routes | Cost / abuse |
| Localhost `NEXT_PUBLIC_API_URL` fallback | Frontend services | Production browser talks to user localhost |
| In-memory opportunities only | `OpportunityStore` | Apparent “data loss” on every deploy/restart |
| History soft-fail | Persist failures don’t fail Analyze | Possible silent non-save if DB misconfigured |
| Duplicate CA filename with spaces | `prod-ca-2021 (1).crt` | Operator confusion if committed |

---

## 2. Remaining blockers

1. **BLOCKED — Source control:** Phase 5.5 / 6.0.2 / 6.0.3 implementation not on `origin/main` (uncommitted).  
2. **BLOCKED — Dependencies:** `pandas-ta==0.3.14b` not installable from current PyPI; unused by app.  
3. **BLOCKED — TLS packaging:** Supabase CA not in remote tree.  
4. **BLOCKED — API exposure:** No non-CORS protection for `/docs`, `/openapi.json`, `POST /opportunities/scan`, and general API.  
5. **BLOCKED — Scale/sleep:** Must commit to single always-on instance or accept duplicate/gap behavior.  
6. **NEEDS CONFIGURATION —** Production env names (`CORS_ORIGINS`, `NEXT_PUBLIC_API_URL`, `PERSISTENCE_ENABLED`, DB URL, `DEBUG=false`) after deployables exist.  
7. **NEEDS CONFIGURATION —** Controlled Alembic upgrade to `0003_decisions_trade_plans` with backup/PITR plan.  
8. **REQUIRES USER DECISION —** Which API privacy mechanism (edge Access vs private service+BFF vs IP allowlist vs deferred public).

---

## 3. Recommended remediation (for a future approved phase)

Order matters; **do not execute** until production-prep is approved:

1. **Curate and commit** the deployable working tree (exclude `.env`, duplicate CA, `.cursor/`). Include `prod-ca-2021.crt` (public CA only) and Alembic.  
2. **Fix requirements:** remove unused `pandas-ta` **or** replace only after a Python **3.12** install matrix proves a pin compatible with locked `pandas`/`numpy`. Prefer removal.  
3. **Choose API protection** that is not CORS; document the chosen pattern. If app-level gating is chosen, that is a separate approved security change.  
4. **Render:** 1× Web Service, always-on, `uvicorn … --host 0.0.0.0 --port $PORT`, health `/api/v1/health`, **no** second scanner worker.  
5. **Supabase:** confirm Session Pooler URL + CA path; backup; then `alembic upgrade head` in a controlled window.  
6. **Vercel:** Root `frontend`; set `NEXT_PUBLIC_API_URL`; enable Deployment Protection for UI.  
7. Smoke-test per `DEPLOYMENT_READINESS_AUDIT.md` §11.

---

## 4. Final production readiness verdict

| Gate | Status |
|------|--------|
| GitHub tree matches local Analyzer (5.5 / 6.0.x) | **FAIL** |
| Backend install reproducible on Render Python | **FAIL** (`pandas-ta`) |
| Supabase TLS artifact deployable | **FAIL** (CA not remote) |
| Direct API protection (non-CORS) | **FAIL** / undecided |
| Single-instance scanner concurrency safety | **PASS** (with ops constraint: 1 instance) |
| Scanner restart durability | **PASS with accepted RAM loss** |
| Migration readiness | **CONDITIONAL** (code present locally; not remote; not executed) |

### Verdict: **NOT READY for production deployment**

This clarification audit confirms and deepens the first audit. Production deployment remains **unapproved**. Stop here pending explicit remediation and deploy approvals.

---

## 5. Preservation note

No trading/SMC/confluence/decision/trade-plan logic, Phase 5.5 scanner behavior, Phase 6.0.3 persistence semantics, schemas, or credentials were modified. No migrations or deploys were run.
