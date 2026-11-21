# Deployment Readiness Audit — Vercel + Render + Supabase

**Status:** AUDIT ONLY (no code, config, schema, migration, or deployment changes were made)  
**Date:** 2026-11-20  
**Target:** Vercel (Next.js) + Render (FastAPI) + existing Supabase PostgreSQL + GitHub CI/CD  
**Scope preserved:** trading/SMC/confluence/decision/trade-plan logic, Phase 5.5 scanner behavior, Phase 6.0.3 persistence, no real trade execution  

Classification legend used below:

| Tag | Meaning |
|-----|---------|
| **READY** | Present and suitable for cloud use as-is |
| **NEEDS CONFIGURATION** | Code exists; production env/settings/process required |
| **BLOCKED** | Must be resolved before a correct production deploy |
| **REQUIRES USER DECISION** | Policy/architecture choice; do not invent silently |

---

## 1. Current architecture

### 1.1 Monorepo layout

| Path | Role |
|------|------|
| `frontend/` | Next.js 16.4.5 App Router UI (Vercel root) |
| `backend/` | FastAPI Python API + WebSockets + in-process scanner |
| `docs/` | Specs, phase docs, QA artifacts |
| `infra/docker/` | Local Dockerfiles (`Dockerfile.api`, `Dockerfile.web`) |
| `docker-compose.yml` | Local api/web/db (+ optional redis) |
| Root `.env.example` | Documented env **names** (template only) |

**Frontend root:** `frontend/`  
**Backend root:** `backend/`

### 1.2 Git remote and branch

| Item | Finding | Class |
|------|---------|-------|
| Remote | `origin` → `https://github.com/Ahmadsh64/ai-crypto-chart-analyst.git` | READY |
| Deploy branch (current) | `main` tracks `origin/main` | READY |
| Working tree vs remote | Large set of **modified + untracked** Phase 5.5 / 6.0.x files not on `origin/main` | **BLOCKED** |

**Critical:** `origin/main` does **not** contain local scanner (`backend/app/scanner/`), DB layer (`backend/app/db/`), Alembic (`backend/alembic*`), history/opportunities routes, Market Opportunities / History frontend pages, or `frontend/vercel.json`.  

A Vercel/Render deploy from GitHub **today** would ship an **older incomplete tree**, not the local AI Market Analyzer you are running.

### 1.3 Runtime versions and commands

| Area | Finding | Class |
|------|---------|-------|
| Next.js | `16.4.5` in `frontend/package.json` | READY |
| Frontend scripts | `dev` / `build` / `start` / `test` (`tsx --test`) / `lint` | READY |
| Frontend Vercel hints | `frontend/vercel.json` → `npm install` + `npm run build` (local/untracked relative to remote) | NEEDS CONFIGURATION |
| Python (local) | 3.13.1 observed | NEEDS CONFIGURATION |
| Python (Docker API image) | `python:3.12-slim` | READY (prefer for Render) |
| Backend deps | `backend/requirements.txt` (pinned FastAPI/uvicorn/SQLAlchemy/asyncpg/…) | NEEDS CONFIGURATION |
| `pandas-ta==0.3.14b` | Listed; **not imported** by app code; install may fail on some Python indexes/versions | **BLOCKED** (install risk) |
| Backend tests | `pytest` via `requirements.txt` / setup guide | READY |
| Docker Compose | Dev-oriented (`--reload`, `npm run dev`) | READY for local only |
| Production Docker | API CMD binds `0.0.0.0:8000`; web Dockerfile still `npm run dev` | NEEDS CONFIGURATION |

### 1.4 Environment variable **names** (values never recorded)

**Frontend (browser-safe):**

- `NEXT_PUBLIC_API_URL`
- `NEXT_PUBLIC_APP_NAME`

**Backend / shared (server-only; never `NEXT_PUBLIC_*`):**

- `ENVIRONMENT`
- `DEBUG`
- `DEMO_MODE`
- `HOST`
- `PORT`
- `CORS_ORIGINS`
- `API_V1_PREFIX`
- `PERSISTENCE_ENABLED`
- `DATABASE_URL`
- `DATABASE_ECHO`
- `SUPABASE_DB_URL`
- `SUPABASE_DB_HOST`
- `SUPABASE_DB_PORT`
- `SUPABASE_DB_NAME`
- `SUPABASE_DB_USER`
- `SUPABASE_DB_PASSWORD`
- `SUPABASE_SSL_CA_FILE`
- `DB_POOL_SIZE`
- `DB_MAX_OVERFLOW`
- `DB_POOL_TIMEOUT_SECONDS`
- `DB_CONNECT_TIMEOUT_SECONDS`
- `REDIS_URL`
- `REDIS_ENABLED`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `OPENAI_VISION_MODEL`
- `OPENAI_EXPLAINER_MODEL`
- `OPENAI_TIMEOUT_SECONDS`
- `OPENAI_MAX_RETRIES`
- `BINANCE_BASE_URL`
- `BINANCE_FUTURES_BASE_URL`
- `BYBIT_BASE_URL`
- `DEFAULT_ACCOUNT_BALANCE`
- `DEFAULT_RISK_PERCENT`
- `DEFAULT_MIN_RISK_REWARD`
- `MAX_RISK_PERCENT`
- `MAX_UPLOAD_SIZE_MB`
- `ALLOWED_IMAGE_TYPES`
- `MAX_IMAGE_WIDTH`
- `MAX_IMAGE_HEIGHT`
- `MIN_IMAGE_WIDTH`
- `MIN_IMAGE_HEIGHT`

**Note:** `backend/app/core/security.py` mentions optional `APP_API_KEY` behavior via `app_api_key`, but **Settings does not define** that field and **no route uses** `verify_optional_api_key`. Treat as unused stub — **REQUIRES USER DECISION** before relying on it.

### 1.5 Data flow (deployed shape)

```text
Browser (Vercel)
  ├─ HTTPS REST  → NEXT_PUBLIC_API_URL → Render FastAPI (/api/v1/*)
  └─ WSS         → same origin host     → Render (/ws/market, /ws/replay)

Render FastAPI process
  ├─ Exchange public REST/WS (Binance, Bybit)
  ├─ Optional OpenAI (vision/explainer)
  ├─ In-process Phase 5.5 scanner loop (300s)
  ├─ In-memory OpportunityStore
  └─ Optional async SQLAlchemy → Supabase Session Pooler (TLS + CA)
```

---

## 2. Frontend — Vercel readiness

| Check | Finding | Class |
|-------|---------|-------|
| Production build command | `npm run build` then `npm run start` (Vercel handles start) | READY |
| Root directory | Must be `frontend` | NEEDS CONFIGURATION |
| API base URL | `process.env.NEXT_PUBLIC_API_URL` in `services/api.ts`, `market-websocket.ts`, `replay-websocket.ts` | NEEDS CONFIGURATION |
| Localhost fallback | Defaults to `http://127.0.0.1:8000` if env unset — **dangerous in production** | **BLOCKED** until prod env set (and ideally fail-closed later) |
| Hardcoded localhost in prod paths | Only as **fallback** when env missing; no other hardcoded hosts found in TS services | NEEDS CONFIGURATION |
| Server secrets in browser | No `OPENAI_*` / `DATABASE_*` / Supabase passwords in frontend code | READY |
| Upload workflow | Client → `POST` multipart AI vision routes; validation server-side | READY (needs CORS + backend) |
| Live Market / Analyzer | REST + `/ws/market` (http→ws / https→wss rewrite) | READY (needs persistent backend) |
| History page | `frontend/app/(app)/history/` + history API client | READY locally; **BLOCKED** on GitHub until committed |
| Market Opportunities | `frontend/app/(app)/market-opportunities/` + opportunities API | READY locally; **BLOCKED** on GitHub until committed |
| Routing / refresh | App Router pages under `app/(app)/…`; standard Next refresh | READY |
| `vercel.json` | Present under `frontend/` (framework nextjs, install/build) | NEEDS CONFIGURATION (Root Directory) |

### Exact Vercel project settings (required)

| Setting | Value |
|---------|-------|
| Framework preset | Next.js |
| Root Directory | `frontend` |
| Install Command | `npm install` (or lockfile-aware `npm ci` if preferred) |
| Build Command | `npm run build` |
| Output | Default Next.js (no static export) |
| Node | 20.x or 22.x (align with local 22) |
| Env (Production) | `NEXT_PUBLIC_API_URL` = `https://<render-service>.onrender.com` (no trailing slash) |
| Env (Production) | `NEXT_PUBLIC_APP_NAME` = `AI Crypto Chart Analyst` (or product name) |
| Deployment Protection | **Recommended** for private preview (see §6) | REQUIRES USER DECISION |

---

## 3. Backend — Render readiness

| Check | Finding | Class |
|-------|---------|-------|
| App entry | `app.main:app` | READY |
| Host binding | Settings default `HOST=0.0.0.0`; local README uses `127.0.0.1` (wrong for cloud) | NEEDS CONFIGURATION |
| `PORT` | Settings has `port`; **uvicorn CLI must use `$PORT`** on Render | NEEDS CONFIGURATION |
| Health | `GET /api/v1/health` (api, database, exchanges, openai) | READY |
| CORS | `CORS_ORIGINS` comma-list; defaults localhost only | NEEDS CONFIGURATION |
| Docs exposure | `/docs` and `/redoc` always enabled in `create_app()` | **REQUIRES USER DECISION** (security) |
| Supabase URL | `DATABASE_URL` / `SUPABASE_DB_URL` / discrete `SUPABASE_DB_*` | NEEDS CONFIGURATION |
| TLS CA | Verifying `SSLContext` (`CERT_REQUIRED`, hostname check); CA file `prod-ca-2021.crt` | NEEDS CONFIGURATION |
| CA in Git | `backend/prod-ca-2021.crt` exists locally, **not tracked on origin** | **BLOCKED** for clean cloud SSL unless packaged |
| Migrations | Alembic revisions `0001` → `0002` → **`0003_decisions_trade_plans` (head)** | NEEDS CONFIGURATION (run manually; not auto) |
| OpenAI | Optional; missing key → soft-fail / unavailable components | READY |
| Binance / Bybit | Public REST base URLs configurable; no trading keys | READY |
| WebSockets | `/ws/market`, `/ws/replay` on same process | READY; needs always-on single instance |
| Uploads | In-memory validation via Pillow; no durable upload disk path | READY |
| Persistence soft-fail | Analyze continues if DB down when designed soft-persist | READY |

### Suggested Render Web Service (no code changes yet)

| Setting | Recommended value |
|---------|-------------------|
| Type | **Web Service** (not serverless) |
| Root Directory | `backend` |
| Runtime | Python 3.12 |
| Build Command | `pip install -r requirements.txt` (**blocked** until `pandas-ta` pin resolves) |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/v1/health` |
| Instances | **1** (see §4) |
| Plan | Always-on (free tier sleep breaks WS + scanner) | REQUIRES USER DECISION |

### Background Worker

| Option | Verdict |
|--------|---------|
| Separate Render Background Worker running a second scanner | **Do not add** — would create a **second scheduler** unless web disables scanner (behavior change) |
| Worker-only scanner + API without scanner | Architectural split; **out of scope** without approved design |
| Safest now | Scanner stays **inside** the single FastAPI Web Service | READY (recommendation) |

---

## 4. Scheduler and scanner architecture

### 4.1 How it works today

| Topic | Finding | Class |
|-------|---------|-------|
| Location | Started in FastAPI `lifespan` via `get_scanner().start()` | READY |
| Interval | `scan_interval_seconds` default **300** (5 minutes) | READY |
| Continuous process | Yes — `asyncio` loop in the API process | READY |
| Overlap lock | `asyncio.Lock` in `MarketOpportunityScanner` — **process-local** | READY (single instance only) |
| Store | In-memory `OpportunityStore` (thread `Lock`) — **not** Postgres | READY / risk |
| Restart survival | Opportunities + scan history **lost** on process restart; next loop scan rebuilds | NEEDS CONFIGURATION (ops expectation) |
| Failed / interrupted scans | Loop catches errors, sets store `error`, waits interval, continues; in-flight cancel on shutdown | READY |
| Manual trigger | Unauthenticated `POST /api/v1/opportunities/scan` | Security risk — see §6 |
| Multi-instance | Each instance runs its **own** loop + lock + memory → **duplicate scans** + inconsistent API reads | **BLOCKED** if scaled >1 |
| WebSockets | Persistent connections to the same process that holds streams | Requires sticky/single instance |

### 4.2 Scheduler deployment recommendation (no behavior change)

**Recommend:**

1. **One** Render Web Service instance.  
2. Keep the **existing in-process** 5-minute scanner (do **not** deploy a Background Worker scheduler).  
3. Do **not** introduce a second scheduler.  
4. Accept empty Opportunities UI until the first post-boot scan completes.  
5. If later multi-instance is required: stop and redesign distributed lock + shared store (**REQUIRES USER DECISION**; not part of this deploy).

| Arrangement | Class |
|-------------|-------|
| Single Web Service + in-process scanner | READY (safest) |
| Web + Background Worker both scanning | **BLOCKED** (duplicate scheduler) |
| Horizontal scale of Web Service | **BLOCKED** until distributed coordination exists |

---

## 5. Supabase production safety

| Check | Finding | Class |
|-------|---------|-------|
| Existing DB | Project already uses Supabase PostgreSQL with optional persistence | READY |
| App flag | `PERSISTENCE_ENABLED` must be `true` in production for History soft-persist | NEEDS CONFIGURATION |
| Pooler | Docs/example point at Supabase **Session Pooler** host on port **5432** style URLs | NEEDS CONFIGURATION |
| SQLAlchemy pool | `DB_POOL_SIZE` default 5, `DB_MAX_OVERFLOW` 10, `pool_pre_ping` | READY |
| SSL | Explicit CA verification for Supabase URLs; never `CERT_NONE` | READY |
| CA path | `SUPABASE_SSL_CA_FILE` or default `backend/prod-ca-2021.crt` | NEEDS CONFIGURATION |
| Alembic head | `0003_decisions_trade_plans` | READY (code) |
| Migration execution | Manual `alembic upgrade head` from `backend/` with env loaded — **not** run by this audit | NEEDS CONFIGURATION |
| Auto-migrate on boot | Not present (good for safety) | READY |
| Backups | Ops responsibility (Supabase PITR / `pg_dump`); not automated in repo | REQUIRES USER DECISION |
| Credentials in Git | `.env` gitignored; ensure CA-only public cert if committed — **no passwords** | NEEDS CONFIGURATION |

**Do not execute migrations as part of deploy until:** (a) deployable commit is on GitHub, (b) production URL + CA confirmed, (c) explicit user approval.

---

## 6. Security and remote access

| Area | Finding | Class |
|------|---------|-------|
| User authentication | **None** approved / implemented | READY (fact) / risk |
| Public API | All `/api/v1/*` and WS routes open | **BLOCKED** for “private” unless edge protection |
| CORS | Must allow only Vercel origin(s) | NEEDS CONFIGURATION |
| Secret management | Server env on Render; only `NEXT_PUBLIC_*` on Vercel | NEEDS CONFIGURATION |
| Upload validation | Size, format, dimensions; re-encode PNG; no persistent store | READY |
| Admin-like endpoint | `POST /api/v1/opportunities/scan` unauthenticated | **BLOCKED** for open internet |
| Rate limiting (app) | No global API rate limit; exchange client retries only | **BLOCKED** / gap |
| OpenAPI UI | `/docs`, `/redoc` public | REQUIRES USER DECISION |
| Optional API key helper | Unused stub; Settings field missing | REQUIRES USER DECISION |

### Practical privacy for **initial** deploy (no auth feature work)

Recommended layered approach (**REQUIRES USER DECISION** on which combo):

1. **Vercel Deployment Protection** (password / SSO) so the UI is not public.  
2. **Do not share** Render URL; restrict `CORS_ORIGINS` to the Vercel production domain only (browsers blocked; raw curl still works).  
3. Prefer Render **non-sleeping** private networking / IP allowlist **if** your Render plan supports it; otherwise accept that API remains reachable by URL.  
4. Optional edge: Cloudflare Access / tunnel in front of API (ops, not code).  
5. Keep `DEBUG=false`, `ENVIRONMENT=production`.  
6. Defer public launch until an approved auth design exists.

**Do not** implement authentication in this phase without approval.

---

## 7. Deployment blockers (summary)

| # | Blocker | Class |
|---|---------|-------|
| B1 | Deployable Phase 5.5 / 6.0.x tree **not on `origin/main`** | **BLOCKED** |
| B2 | `pandas-ta==0.3.14b` may fail `pip install` on Render | **BLOCKED** |
| B3 | Supabase CA file not in Git remote artifact | **BLOCKED** (SSL) |
| B4 | No auth + open `POST /opportunities/scan` + open `/docs` | **BLOCKED** for private/public safety |
| B5 | Multi-instance / free-tier sleep incompatible with scanner + WS | **BLOCKED** if chosen |
| B6 | Production `NEXT_PUBLIC_API_URL` + `CORS_ORIGINS` not set yet | NEEDS CONFIGURATION |
| B7 | Alembic head must be applied intentionally on prod DB | NEEDS CONFIGURATION |
| B8 | Localhost API fallback if frontend env missing | **BLOCKED** until env guaranteed |

---

## 8. Required configuration changes (planned; not applied)

These are **configuration / process** items for a later implementation PR — listed for readiness only:

1. Commit/push the current feature tree (or a release branch) including backend db/scanner/alembic, frontend history/opportunities, CA cert (public), `vercel.json`.  
2. Fix or remove the failing `pandas-ta` pin for reproducible Python 3.12 installs.  
3. Render start: `--host 0.0.0.0 --port $PORT`.  
4. Set production env names (see §9).  
5. Single instance; always-on plan.  
6. Decide privacy controls (Vercel protection / edge) before sharing URLs.  
7. Decide whether to disable `/docs` in production (code change later).  
8. Run `alembic upgrade head` once against production with approval.

**Out of scope / forbidden without approval:** trading logic, SMC formulas, confluence weights, decision/trade-plan eligibility, Phase 6.0.3 persistence semantics, schema changes, Phase 5.5 scanner behavior changes, credentials in Git, real trade execution, second scheduler.

---

## 9. Exact deployment settings

### 9.1 Vercel

1. Connect GitHub repo `Ahmadsh64/ai-crypto-chart-analyst`.  
2. Production branch: `main` (or a dedicated `release/*` — **REQUIRES USER DECISION**).  
3. Root Directory: `frontend`.  
4. Build: `npm run build`.  
5. Env: `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_APP_NAME`.  
6. Enable Deployment Protection for private beta.  
7. Note production domain: `https://<project>.vercel.app` (or custom domain).

### 9.2 Render

1. New **Web Service** from same GitHub repo.  
2. Root Directory: `backend`.  
3. Build: `pip install -r requirements.txt` (after B2 fixed).  
4. Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.  
5. Health: `/api/v1/health`.  
6. Instances: **1**.  
7. **No** Background Worker for scanner.  
8. Env names (set values in Render dashboard only):

| Name | Notes |
|------|-------|
| `ENVIRONMENT` | `production` |
| `DEBUG` | `false` |
| `DEMO_MODE` | `false` |
| `CORS_ORIGINS` | Exact Vercel origin(s), comma-separated |
| `PERSISTENCE_ENABLED` | `true` if History required |
| `DATABASE_URL` or `SUPABASE_DB_URL` | Session pooler URL (asyncpg form OK; app normalizes) |
| `SUPABASE_SSL_CA_FILE` | e.g. `prod-ca-2021.crt` |
| `OPENAI_API_KEY` | Optional |
| `OPENAI_MODEL` / `OPENAI_VISION_MODEL` / `OPENAI_EXPLAINER_MODEL` | Optional overrides |
| `BINANCE_BASE_URL` / `BINANCE_FUTURES_BASE_URL` / `BYBIT_BASE_URL` | Defaults OK |
| Upload/risk knobs | Optional; defaults exist |

Render injects `PORT` automatically — do not hardcode `8000` in the start command.

### 9.3 Supabase

1. Use **Session Pooler** connection string suitable for long-lived app connections (confirm port/mode with current Supabase UI).  
2. Ensure TLS CA file is present on the Render filesystem (repo file or secret file mount).  
3. Migration procedure (manual, approved):

```text
cd backend
# with production env loaded (no secrets in shell history dumps / tickets)
alembic upgrade head
```

4. Verify with health `database` component `ok`.  
5. Confirm backup/PITR policy in Supabase dashboard (**REQUIRES USER DECISION**).

### 9.4 Integration

| Step | Action |
|------|--------|
| API URL | Vercel `NEXT_PUBLIC_API_URL` → Render HTTPS origin |
| WS | Client rewrites `https`→`wss` to `/ws/market` |
| CORS | Render `CORS_ORIGINS` includes Vercel origin |
| Health | Render health check + external smoke `GET /api/v1/health` |
| Order | Migrate DB → deploy Render → set Vercel env → deploy Vercel |

---

## 10. Deployment sequence

1. **User decision:** privacy method, Render plan, branch name, whether OpenAI is required.  
2. Resolve **B1–B3** (commit tree, deps install, CA packaging) in a dedicated change set (later).  
3. Apply Alembic to production Supabase (approved window).  
4. Create Render Web Service (1 instance); confirm health + DB + exchanges.  
5. Create Vercel project; set `NEXT_PUBLIC_API_URL`; enable protection.  
6. Set Render `CORS_ORIGINS` to Vercel URL; redeploy if needed.  
7. Run smoke tests (§11).  
8. Only then share access with trusted testers.

---

## 11. Smoke-test checklist

- [ ] `GET https://<render>/api/v1/health` → overall not `unavailable`; `database` ok if persistence on  
- [ ] `GET /api/v1/market/...` candles/ticker for Binance + Bybit sample symbols  
- [ ] Vercel loads `/dashboard`, `/live-market`, `/chart-analyzer`  
- [ ] Live chart WebSocket connects (`wss://…/ws/market`) and receives ticks  
- [ ] Live Market Analyze returns decision/trade levels (deterministic path)  
- [ ] Uploaded Image Analysis accepts PNG/JPEG and soft-fails AI if key absent  
- [ ] History lists/detail when persistence enabled  
- [ ] Market Opportunities page loads; after ≤5 minutes scanner shows status/results  
- [ ] Manual scan trigger behavior understood (and access restricted outside prod)  
- [ ] CORS: browser calls from Vercel succeed; random origins fail  
- [ ] No secrets in browser network payloads / JS bundles (`NEXT_PUBLIC_*` only)  
- [ ] Process restart: Opportunities empty then refill; History DB rows remain  

---

## 12. Rollback plan

| Layer | Rollback |
|-------|----------|
| Vercel | Redeploy previous deployment / promote prior immutable deployment |
| Render | Redeploy previous successful deploy; keep instance count at 1 |
| Frontend env mistake | Fix `NEXT_PUBLIC_API_URL` and redeploy Vercel |
| Backend env mistake | Fix Render env; restart service |
| Bad migration | **Do not** auto-downgrade blindly; restore from Supabase backup/PITR; Alembic downgrade only with explicit DBA approval |
| Scanner overload | Temporary: set ops process to stop service / later config flag (not inventing new scheduler) |
| Security incident | Rotate `OPENAI_API_KEY` and DB password; revoke leaked URLs; enable stronger edge protection |

---

## 13. Security risks (explicit)

1. Unauthenticated public API surface (analysis, history if enabled, opportunities, scan trigger).  
2. Public OpenAPI docs revealing route map.  
3. Cost abuse via OpenAI vision uploads if key configured and URL leaked.  
4. Exchange rate-limit pressure from scanner + users on one IP.  
5. In-memory opportunities not durable / not shared — misleading under scale.  
6. Accidental localhost API URL in production build if env missing.  
7. Deploying from stale GitHub `main` silently omitting security/persistence features.

---

## 14. Itemized readiness matrix

| Item | Class |
|------|-------|
| Monorepo structure | READY |
| GitHub remote exists | READY |
| GitHub content matches local deployable app | **BLOCKED** |
| Next.js production build capability | READY |
| Vercel root/build settings | NEEDS CONFIGURATION |
| Frontend API/WS env wiring | NEEDS CONFIGURATION |
| Frontend localhost fallback | **BLOCKED** until env guaranteed |
| Backend FastAPI entry + health | READY |
| Render host/`PORT` start command | NEEDS CONFIGURATION |
| CORS for Vercel domain | NEEDS CONFIGURATION |
| Supabase TLS + pooler wiring | NEEDS CONFIGURATION |
| CA cert in deploy artifact | **BLOCKED** |
| Alembic head `0003_…` | READY (code) |
| Production migration execution | NEEDS CONFIGURATION |
| OpenAI optional behavior | READY |
| Public market data connectivity | READY |
| WebSocket persistent hosting | NEEDS CONFIGURATION (always-on, 1 instance) |
| Upload validation | READY |
| In-process 5-min scanner | READY |
| Separate Background Worker scanner | **BLOCKED** (duplicate) / not recommended |
| Multi-instance safe scanning | **BLOCKED** |
| Distributed overlap lock | Not present — single instance only |
| User authentication | Absent — REQUIRES USER DECISION for private access method |
| Rate limiting / abuse controls | Gap — **BLOCKED** for open internet |
| `pandas-ta` dependency install | **BLOCKED** |
| Credentials kept out of Git | READY (process) / verify before commit |
| Real trade execution | Not present (analysis-only) — READY |

---

## 15. Stop point

This document is the **only** deliverable of the audit phase.

**No deployments were performed. No migrations were executed. No secrets were printed. No application code or schemas were modified for deployment.**

Await review and explicit approval before any configuration PR, Git push of deploy artifacts, Render/Vercel provisioning, or production `alembic upgrade`.
