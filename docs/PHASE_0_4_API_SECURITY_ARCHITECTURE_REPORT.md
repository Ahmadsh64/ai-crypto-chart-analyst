# Phase 0.4 — Personal Beta API Security Architecture Report

**Mode:** Read-only audit + architecture proposal (no implementation)  
**Date:** 2026-11-21  
**Audience:** One authorized personal user → future multi-user SaaS  
**Targets:** Vercel (frontend) · Render (FastAPI) · Supabase (PostgreSQL)

### Compliance this phase

| Constraint | Status |
|------------|--------|
| No analysis / scanner / schema / migration / dependency changes | Met |
| No deploy / public exposure / stage / commit / Git history edits | Met |
| Phase 0 backup preserved | Met (untouched) |
| CORS not treated as authentication | Affirmed in findings |

---

## 1. Current security findings

### 1.1 Frontend ↔ backend communication

| Fact | Evidence |
|------|----------|
| All API calls are **browser-side** | `frontend/services/api.ts` uses `fetch(`${API_URL}…`)` with `NEXT_PUBLIC_API_URL` |
| No Next.js Route Handlers / BFF | `frontend/app/api/**` does **not** exist |
| WebSockets are browser-side | `market-websocket.ts`, `replay-websocket.ts` rewrite API URL → `ws`/`wss` |
| Pages are client components | e.g. `chart-analyzer/page.tsx` `"use client"` + imports `@/services/api` |
| Public env only | `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_APP_NAME` — no server secrets in frontend env names |

**Implication:** Anything put in the browser (API keys, Cloudflare service tokens, shared secrets) is extractable. Secrets must stay on servers or at an edge identity layer that issues **user-bound** sessions (cookies), not embeddable static tokens.

### 1.2 Backend authentication

| Item | Finding |
|------|---------|
| Enforced auth on routes | **None** — no `Depends(...)` auth on routers |
| Helper stub | `backend/app/core/security.py` → `verify_optional_api_key` |
| Stub usability | **Broken / unused** — reads `settings.app_api_key` via `getattr`, but `Settings` has **no** `app_api_key` field; **no route imports** this helper |
| User accounts / sessions / JWT | **Not present** |
| Rate limiting (app-level) | **Not present** (exchange client retries only) |

### 1.3 CORS

```text
CORSMiddleware(
  allow_origins=settings.cors_origin_list,  # default localhost:3000
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)
```

CORS only limits **browser** cross-origin XHR/fetch. It does **not** stop curl, bots, OpenAPI explorers, or scripts. **Not authentication.**

### 1.4 Docs / OpenAPI exposure

| Path | Status |
|------|--------|
| `/docs` | Always enabled (`docs_url="/docs"`) |
| `/redoc` | Always enabled |
| `/openapi.json` | Default FastAPI exposure |
| `/` | Public service card pointing at docs + health |

### 1.5 High-risk / administrative surfaces

| Route | Risk |
|-------|------|
| `POST /api/v1/opportunities/scan` | Triggers full market scan — unauthenticated cost/load |
| `POST /api/v1/ai/*` (analyze, vision, compare) | OpenAI cost abuse if key configured |
| `POST/DELETE /api/v1/replay/sessions…` | Session/control surface; resource use |
| History GETs | Leak persisted analyses if DB enabled |
| Opportunities GETs | Leak scanner results |
| `/ws/market`, `/ws/replay` | Persistent unauthenticated streams |

### 1.6 Secrets handling

| Secret class | Location | Browser exposure? |
|--------------|----------|-------------------|
| `OPENAI_API_KEY`, DB URLs/passwords, Supabase | Backend env only | No (by design) |
| `NEXT_PUBLIC_*` | Frontend bundle | Yes — must stay non-secret |
| `.env` / `.env.local` | Gitignored | Local only |

No evidence of service-role keys or DB passwords in frontend source.

### 1.7 Deployment / reverse-proxy config

| Artifact | Finding |
|----------|---------|
| `frontend/vercel.json` | Framework/install/build only — no auth, no rewrites to backend |
| Render config | Not in-repo yet (start command / IP rules / private service — ops) |
| Docker Compose | Local only; API public on 8000 |

**Vercel Deployment Protection does not secure the Render hostname.**

---

## 2. Existing authentication mechanisms

| Mechanism | Present? | Effective? |
|-----------|----------|------------|
| User login / OAuth / Supabase Auth | No | — |
| Session cookies | No | — |
| Working API-key gate | Stub only | **No** |
| Edge access control | No | — |
| BFF / same-origin proxy | No | — |
| CORS allowlist | Yes | Browser UX only |

---

## 3. Exposed routes and risks (summary)

**Access requirement today: none (public if URL known).**

Grouped surfaces under `/api/v1` (+ WS):

| Group | Examples | Personal-beta risk |
|-------|----------|--------------------|
| Health | `GET /health` | Low info leak; useful for probes |
| Market | exchanges, markets, candles, ticker | Exchange rate-limit / scraping |
| Analysis engines | indicators, structure, liquidity, OB/FVG, MTF, confluence, trade-plan, decision | CPU + data abuse |
| AI | `/ai/analyze`, vision upload, compare | **Cost** |
| History | analyses list/detail | Privacy of saved runs |
| Opportunities | list/status/history/`POST /scan` | **Scan abuse** |
| Replay | large session/control/report API | Resource abuse |
| WebSocket | `/ws/market`, `/ws/replay` | Persistent load |
| Docs | `/docs`, `/redoc`, `/openapi.json` | Attack surface map |

Scanner **scheduler** runs in-process regardless of auth; `POST /scan` adds an unauthenticated **manual** trigger.

---

## 4. Recommended personal-beta architecture

### Recommendation (primary)

**Edge identity (Cloudflare Access or equivalent) in front of the Render API hostname, plus Vercel access control for the UI, plus FastAPI hardening (docs off in production, strict CORS).**

Do **not** embed Cloudflare Access **service tokens** (or any shared API secret) in browser JavaScript.

```text
Authorized user
    │
    ├─ HTTPS → Vercel (UI)
    │     Cloudflare Access / Vercel Deployment Protection
    │     (same authorized email / IdP policy)
    │
    └─ HTTPS/WSS → Render FastAPI (direct from browser today)
          Cloudflare Access session cookie / JWT for that host
          CORS_ORIGINS = https://<vercel-domain> only
          /docs /redoc /openapi.json disabled when ENVIRONMENT=production
```

**Why this fits the current app**

- Frontend already calls Render **from the browser** (REST + WebSocket). Edge Access protects **both** REST and `wss://` without rewriting the client to a BFF first.
- Secrets (`OPENAI_API_KEY`, DB) remain on Render only.
- One authorized personal user = Access allowlist (email / Google account).
- Analysis / scanner engines unchanged.

**Browser authentication flow**

1. User opens Vercel URL → Access (or Vercel Protection) challenges → proves identity.  
2. User’s browser later calls `NEXT_PUBLIC_API_URL` (Render) → Access challenges that host (first time) → same IdP / allowed email.  
3. Subsequent API/WS requests carry Access session cookies for the Render host.  
4. Unauthenticated requests never reach FastAPI (or are rejected at edge).

**Optional defense-in-depth (later, still not in browser):** machine-only `APP_API_KEY` for ops scripts; never shipped to Next public env.

### Security boundaries

| Layer | Protects | Does not protect alone |
|-------|----------|-------------------------|
| Vercel Protection / Access on UI | UI discovery | Render API URL |
| Cloudflare Access on Render | API + WS + docs if still enabled | Misconfigured allow-all policies |
| Strict CORS | Casual browser abuse from other sites | Non-browser clients |
| Docs disabled | Schema disclosure | Authenticated attackers |

---

## 5. Alternative approaches and trade-offs

### A. Application-level shared secret only (`X-API-Key`)

| Aspect | Assessment |
|--------|------------|
| Security | If sent from browser → **secret leaked**. If only from BFF → OK for REST |
| WS | Needs separate ticket/JWT design |
| Future SaaS | Poor fit as sole user identity |
| Fit with current FE | Unsafe without BFF |

### B. Vercel server-side BFF / Route Handlers proxy

| Aspect | Assessment |
|--------|------------|
| Security | Strong for REST: browser → same-origin `/api/*` → Vercel server adds backend credential |
| Secrets | Stay server-side |
| Compatibility | Requires rewriting `api.ts` (and uploads) to relative `/api/...` |
| Scanner / WS | REST scan OK via proxy; **live WebSockets do not proxy cleanly** through serverless BFF — still need Access/JWT on Render for `/ws/*` |
| Future SaaS | Good stepping stone (swap key for user session JWT at BFF) |

### C. Cloudflare Access / edge only (recommended core)

| Aspect | Assessment |
|--------|------------|
| Security | Strong for personal beta; identity at edge |
| Secrets | No static token in JS |
| Compatibility | Minimal frontend code change |
| Scanner | `POST /scan` and scheduled scanner protected from public internet |
| Future SaaS | Replace/augment Access with app user auth; engines untouched |

### D. Render Private Service + only Vercel can reach it

| Aspect | Assessment |
|--------|------------|
| Security | Strong network isolation |
| Browser | **Cannot** call private service directly — **requires BFF** |
| WS | Harder (private network from Vercel serverless limitations) |
| Complexity | Higher for current client-side WS architecture |

---

## 6. Exact proposed file changes (implementation plan — **not applied**)

Awaiting approval. Proposed minimal set:

| File | Proposed change |
|------|-----------------|
| `backend/app/core/config.py` | Add `app_api_key: str = ""` (optional); add `docs_enabled: bool` or derive from `environment == "production"` → disable docs |
| `backend/app/main.py` | Set `docs_url`/`redoc_url`/`openapi_url` to `None` when docs disabled; keep CORS from env |
| `backend/app/core/security.py` | Repair optional API-key helper to use real Settings field; optionally add middleware or router dependency **only if** approved for non-browser callers |
| `backend/app/api/routes/*.py` | Optionally attach dependency to all routers **except** maybe health — **only if** choosing app-key or JWT path |
| `.env.example` | Document `APP_API_KEY` (empty), `CORS_ORIGINS`, `DOCS_ENABLED` / production docs policy — **names only** |
| `frontend/services/api.ts` (+ WS clients) | **If BFF chosen:** point to same-origin `/api/...`; **If Access-only:** may remain `NEXT_PUBLIC_API_URL` |
| `frontend/app/api/[...path]/route.ts` (new) | **If BFF chosen:** proxy to Render with server-only credential |
| `docs/` | Ops runbook for Cloudflare Access policies on Vercel + Render hosts |

**Not modified in that plan:** scanner algorithms, SMC/ICT/AI math, migrations, schemas, trading logic.

### How the authorized personal user authenticates (recommended path)

- Cloudflare Access (or equivalent) allowlist: **one email / IdP subject**.  
- No password store in the app yet.  
- No multi-user tables yet.

### How protected API routes are secured

- Edge: unauthenticated traffic blocked before FastAPI.  
- App: docs off; CORS = Vercel origin only.  
- Optional later: FastAPI rejects missing/invalid internal key for non-Access clients.

### How unauthenticated requests are rejected

- Edge HTTP 302/403 (Access) for browser and API host.  
- FastAPI 401 only if app-level gate is also enabled for a given path.

### How browser reaches backend securely

- User completes Access for UI and API hosts.  
- REST + WebSocket continue to Render URL with Access session cookies (same pattern as today, with edge in front).

### Future multi-user without rewriting analysis engines

1. Introduce identity at the **edge of the API** (JWT/session middleware) or BFF.  
2. Pass `user_id` / tenant into persistence/history only.  
3. Keep deterministic engines (`decision`, `trade_plan`, scanner analyze) **identity-agnostic**.  
4. Replace personal Access allowlist with Supabase Auth / Auth.js / Clerk at Vercel; validate tokens in FastAPI or BFF.  
5. Row-level filters on History / Opportunities when those become per-user.

---

## 7. Required environment variables (names only)

### Backend (Render) — existing + proposed

| Name | Role |
|------|------|
| `ENVIRONMENT` | Use `production` to drive docs-off policy |
| `DEBUG` | `false` in beta |
| `CORS_ORIGINS` | Exact Vercel origin(s) |
| `PERSISTENCE_ENABLED` / `DATABASE_URL` or `SUPABASE_DB_*` / `SUPABASE_SSL_CA_FILE` | Existing DB |
| `OPENAI_API_KEY` | Existing optional AI |
| `APP_API_KEY` | **Proposed optional** server-only (never `NEXT_PUBLIC_`) |
| `DOCS_ENABLED` | **Proposed optional** explicit override |

### Frontend (Vercel)

| Name | Role |
|------|------|
| `NEXT_PUBLIC_API_URL` | Render HTTPS origin (Access-protected) |
| `NEXT_PUBLIC_APP_NAME` | Display |
| `BACKEND_API_URL` / `BACKEND_API_KEY` | **Only if BFF approved** — server-only on Vercel |

### Edge / ops (not in app code)

| Name | Role |
|------|------|
| Cloudflare Access application policies | Allowed email(s) for Vercel + Render hostnames |

**Do not invent secret values in docs or code.**

---

## 8. Future SaaS migration considerations

| Concern | Guidance |
|---------|----------|
| Personal Access → multi-user | Keep engines pure; add auth middleware + ownership on persisted rows |
| BFF | Eases swapping Access cookies for user JWTs on REST |
| WebSockets | Plan early for JWT-on-connect or ticket exchange; Access is a temporary personal-beta fit |
| Scanner | Remains process-singleton; per-user “scan my universe” is a later product decision |
| Supabase | Already server-side; can later enable Auth + RLS without changing SMC math |
| Avoid | Long-lived shared secrets in the browser; coupling engines to Cloudflare |

---

## 9. Confirmation — no changes made

This phase produced **documentation only**.

| Change type | Performed? |
|-------------|------------|
| Application / frontend / backend source edits | **No** |
| Database / migrations | **No** |
| Dependencies | **No** |
| Git stage / commit / push / history | **No** |
| Deployment / public exposure | **No** |
| Phase 0 backup | **Preserved** |

---

## Final status

**AUDIT COMPLETE — AWAITING ARCHITECTURE APPROVAL**

Preferred architecture to approve or reject:

1. **Cloudflare Access (or equivalent) on Render API + Vercel UI** for the single authorized user.  
2. FastAPI hardening: disable docs/OpenAPI in production; strict `CORS_ORIGINS`.  
3. **No** browser-embedded service tokens or API keys.  
4. Defer full BFF unless you prefer same-origin REST now (still need a WS auth story).  
5. Defer multi-user accounts; keep a clean path via edge/BFF identity later.

**STOP.** Await explicit approval of architecture and implementation plan before any code changes.
