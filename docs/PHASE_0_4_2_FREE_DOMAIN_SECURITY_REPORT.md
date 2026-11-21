# Phase 0.4.2 — Free-Domain Security Architecture & PoC Planning

**Mode:** Read-only  
**Date:** 2026-11-21  
**Constraint:** Free hostnames only — `*.vercel.app` + `*.onrender.com` (no purchased custom domain)  
**Audience:** One authorized personal user → future multi-user SaaS  

### Compliance

| Rule | Status |
|------|--------|
| No source / deps / DB / migrate / deploy / Git changes | Met |
| No secrets printed | Met |
| Prior work / Phase 0 backup preserved | Met |

---

## 1. Free-domain compatibility findings

### 1.1 Can Cloudflare Access protect `*.vercel.app` / `*.onrender.com`?

**No — not in the proposed “transparent Access in front of those URLs” form.**

| Requirement (Cloudflare docs) | Free Vercel/Render hostnames |
|-------------------------------|------------------------------|
| Public hostname Access apps need a domain in an **active Cloudflare zone** (full or partial DNS setup) | `vercel.app` / `onrender.com` are **platform-owned** zones — not zones you can add to your Cloudflare account |
| Access application domain dropdown / public hostname | Limited to domains you control on Cloudflare |
| Community evidence | Cloudflare Community: Access cannot protect third-party `.vercel.app` URLs you do not DNS-control; add app auth instead. Render Community: even with Access on a custom domain, `*.onrender.com` remains reachable unless the **app** rejects it |

**Documented conclusion:** Cloudflare Access requires **your** DNS hostname on Cloudflare. It cannot be assumed to wrap default Vercel/Render URLs.

**Cross-site cookie note (from Phase 0.4.1):** Even if Access were somehow available, `vercel.app` → `onrender.com` is cross-site and fragile for Access cookies. Free domains make Access **both unavailable and undesirable** as the primary control.

### 1.2 Implications

| Approach from Phase 0.4 / 0.4.1 | Free-domain viability |
|---------------------------------|----------------------|
| Access on UI + API custom domains | **Out of scope** (no custom domain) |
| Access on free platform domains | **Not compatible** with documented Access DNS prerequisites |
| Security must live in **application identity** (and/or same-origin BFF), not Cloudflare DNS proxy | **Required** |

---

## 2. Architecture comparison

### A. Cloudflare Access with existing free domains

| Criterion | Assessment |
|-----------|------------|
| Works with free domains? | **No** (no Cloudflare zone control over `vercel.app` / `onrender.com`) |
| Browser auth | N/A |
| Backend protection | N/A at edge |
| Scanner / WebSocket | N/A |
| Secrets server-side? | N/A |
| Complexity / cost | Zero Trust free tier exists, but **cannot attach** to these hostnames |
| SaaS migration | Not a foundation without buying a domain later |
| Verdict | **Reject for this constraint set** |

### B. Application-level authentication in FastAPI

| Criterion | Assessment |
|-----------|------------|
| Works with free domains? | **Yes** |
| Browser auth | Login → receive **user** access token (JWT); send `Authorization: Bearer …` on REST; WS ticket/query/first-message |
| Backend protection | FastAPI dependency/middleware rejects missing/invalid JWT on all sensitive routes (+ WS accept) |
| Scanner | `POST /opportunities/scan` requires valid token |
| WebSocket | Validate token at connect (query param or first JSON auth frame). Native `WebSocket` cannot set arbitrary headers |
| Secrets server-side? | **Yes** if using JWT verification secret / Supabase JWT secret / service role only on Render. **Do not** put long-lived shared `APP_API_KEY` in the browser |
| Complexity | Medium; builds on unused stub direction in `security.py` |
| SaaS migration | **Strong** — same JWT path scales to many users |
| Verdict | **Core of the recommendation** |

### C. Vercel BFF/proxy for REST + protected backend

| Criterion | Assessment |
|-----------|------------|
| Works with free domains? | **Yes** (same-origin browser → `*.vercel.app`) |
| Browser auth | Session/cookie on Vercel origin; BFF attaches server-only credential to Render |
| Backend protection | Render accepts only BFF credential (IP still public — must still auth) |
| Scanner | Proxied through BFF — protected if BFF requires login |
| WebSocket | **Not solved by Vercel rewrite/BFF** — browser still opens `wss://*.onrender.com` directly; needs app-level WS auth (tickets/JWT) |
| Secrets server-side? | **Yes** for REST path |
| Complexity | Higher (rewrite all `api.ts` REST; upload proxy; still need WS design) |
| SaaS migration | Good for REST; WS still needs tokens |
| Verdict | **Useful complement**, not sufficient alone |

### D. Supabase Auth as multi-user foundation

| Criterion | Assessment |
|-----------|------------|
| Works with free domains? | **Yes** |
| Browser auth | Supabase Auth (email magic link / password) on Vercel; browser holds **user** JWT (anon key is public-by-design; **service role never in browser**) |
| Backend protection | FastAPI validates Supabase JWT (JWKS or JWT secret on Render) |
| Scanner / WS | Same JWT gate |
| Secrets server-side? | Service role + DB URL + JWT secret on Render only |
| Complexity | Medium; aligns with existing Supabase Postgres |
| SaaS migration | **Best alignment** with stated future |
| Verdict | **Preferred identity provider** for option B |

---

## 3. Current code inspection (exact)

| Area | Location / detail |
|------|-------------------|
| FastAPI entry / CORS / docs | `backend/app/main.py` — open routers; `/docs`+`/redoc` always on; CORS from `CORS_ORIGINS` |
| Routes | `backend/app/api/routes/*` — market, engines, AI, history, opportunities (`POST /scan`), replay, health; WS in `websocket.py` |
| Auth helper | `backend/app/core/security.py` — unused broken stub (`app_api_key` not on `Settings`) |
| Settings | `backend/app/core/config.py` — no auth fields today |
| Frontend REST | `frontend/services/api.ts` — `NEXT_PUBLIC_API_URL`; `fetch` without `credentials`; `Content-Type: application/json` |
| Frontend WS | `market-websocket.ts`, `replay-websocket.ts` — `new WebSocket(wss…/ws/…)` no auth |
| Env template | `.env.example` — `NEXT_PUBLIC_API_URL`, server secrets; no auth vars yet |
| Vercel | `frontend/vercel.json` — build only; no rewrites/BFF |
| Scanner trigger | `POST /api/v1/opportunities/scan` in `opportunities.py` — unauthenticated |

---

## 4. Recommended architecture (free domains)

### Recommendation

**Application-level JWT authentication (prefer Supabase Auth for one personal user now, multi-user later), enforced by FastAPI on all sensitive REST and WebSocket endpoints.**

Optional later: Vercel BFF for REST hygiene — **not required** for the minimum secure personal beta if JWT is validated on Render.

```text
Personal user
  → Vercel UI (*.vercel.app)
       login via Supabase Auth (or equivalent app login)
       browser stores user access_token (not service-role, not shared API key)
  → REST to Render (*.onrender.com)
       Authorization: Bearer <user_jwt>
  → WSS to Render
       connect with short-lived proof (query access_token or first-frame auth)
  → FastAPI verifies JWT; rejects anonymous
  → CORS_ORIGINS = exact Vercel origin (not auth)
  → /docs disabled in production
```

### Why this fits free domains

- No Cloudflare DNS ownership required.  
- Cross-origin works with **Authorization header** (avoids Access cookie / third-party cookie problems from Phase 0.4.1).  
- User JWT in the browser is acceptable; **shared backend secrets are not**.  
- Scanner and AI cost endpoints require a valid user token.  
- Analysis/trading engines stay identity-agnostic; only the HTTP/WS edge checks identity.

### Must-haves

1. Protect **all** app routes except a minimal public surface (e.g. `GET /api/v1/health` **or** make health auth-only too — decide in implementation; prefer health auth-optional for Render probes **or** use Render health with auth bypass only for that path).  
2. Reject unauthenticated `POST /opportunities/scan`.  
3. Reject unauthenticated WS connects.  
4. Never put `SUPABASE_SERVICE_ROLE`, DB passwords, or long-lived `APP_API_KEY` in `NEXT_PUBLIC_*`.  
5. Do not treat CORS as authentication.

### Explicit non-assumptions

- Vercel Deployment Protection ≠ Render API protection.  
- Vercel rewrite/BFF ≠ WebSocket upgrade proxy.

---

## 5. Exact files that would need modification (future approved phase)

| File | Change (proposal only) |
|------|------------------------|
| `backend/app/core/config.py` | Auth-related settings (e.g. JWT secret / Supabase URL / audience); `docs_enabled` |
| `backend/app/core/security.py` | Replace stub with real JWT verification dependency |
| `backend/app/main.py` | Apply auth dependency globally or per-router; disable docs in production |
| `backend/app/api/routes/*.py` | Ensure routes use shared auth dependency (or router-level `dependencies=`) |
| `backend/app/api/routes/websocket.py` + WS managers | Authenticate before `handle_client` |
| `frontend/services/api.ts` | Attach `Authorization` bearer from session |
| `frontend/services/market-websocket.ts` / `replay-websocket.ts` | Pass token on connect |
| New frontend auth UI / provider | Login/logout for personal user |
| `.env.example` | Document auth env **names** only |

**Not modified:** SMC/ICT/AI math, scanner algorithms/schedule, migrations/schemas, trading formulas.

---

## 6. Environment variables required (names only)

### Backend (Render)

| Name | Purpose |
|------|---------|
| `CORS_ORIGINS` | Exact `https://<app>.vercel.app` |
| `ENVIRONMENT` / `DEBUG` | Production hardening / docs off |
| `SUPABASE_URL` or existing DB URL fields | Persistence (existing) |
| `SUPABASE_JWT_SECRET` or JWKS-related settings | **Proposed** JWT verification |
| `OPENAI_API_KEY` | Existing (server-only) |
| Optional `DOCS_ENABLED=false` | Docs gate |

### Frontend (Vercel)

| Name | Purpose |
|------|---------|
| `NEXT_PUBLIC_API_URL` | Render origin (public hostname — OK) |
| `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` | **Only if** Supabase Auth chosen (anon key is public-by-design) |
| Server-only BFF secrets | **Only if** BFF approved later — never `NEXT_PUBLIC_` |

---

## 7. REST and WebSocket authentication design

### REST

1. User authenticates in UI → obtains short-lived **user** access token.  
2. `api.ts` sets `Authorization: Bearer <token>` on every protected call.  
3. FastAPI dependency validates signature/expiry/audience; `401` if invalid.  
4. CORS allows the Vercel origin; preflight is normal FastAPI CORS (no Access OPTIONS bypass needed).

### WebSocket

1. After login, client connects to `wss://<render>/ws/market?access_token=…` **or** sends `{ "action": "auth", "token": "…" }` as first message before subscribe.  
2. Server validates token; close with policy code if missing/invalid.  
3. Do not embed long-lived shared API keys in the WS URL permanently.

### Scanner

- `POST /opportunities/scan` behind the same JWT dependency.  
- Background scheduler remains process-local (ops: single instance); public cannot trigger scans without token.

---

## 8. PoC steps and acceptance criteria

### Locally validatable (no Vercel/Render required)

| Step | How | Pass criteria |
|------|-----|---------------|
| L1 | Run FastAPI with auth middleware prototype against TestClient | Unauthenticated REST → **401** |
| L2 | TestClient with valid test JWT | Authenticated REST → **200** on sample route |
| L3 | Call `POST /opportunities/scan` without token | **401** |
| L4 | Same with token | **200** / skipped-scan business response (not auth failure) |
| L5 | WS connect without token | Rejected / closed |
| L6 | WS connect with token | Accepted; can subscribe |
| L7 | Grep frontend bundle / env for service-role / DB password / shared API key | **No** long-lived server secrets in client |
| L8 | OPTIONS preflight in TestClient/CORS unit expectations | Allowed origin + methods/headers behave; auth not bypassed for POST |

### Requires real free-domain deploy (Vercel + Render)

| Step | Pass criteria |
|------|---------------|
| D1 | From browser on `*.vercel.app`, unauthenticated REST to `*.onrender.com` → **401** (not open 200) |
| D2 | After login, REST analyze/health-protected routes succeed |
| D3 | Unauthorized scan fails; authorized scan works |
| D4 | Unauthenticated WS fails; authenticated WS receives market messages |
| D5 | DevTools: no service-role / DB URL / shared backend master key in JS or `NEXT_PUBLIC_*` |
| D6 | CORS: browser console shows no CORS block for authorized credentialed/headered calls from the Vercel origin |

**PoC rule:** Do not share URLs publicly until D1–D6 pass.

---

## 9. Future multi-user migration plan

1. Keep engines pure (no user logic inside SMC/decision/scanner formulas).  
2. Expand Supabase Auth (or IdP) from 1 user to N.  
3. Add `user_id` / tenant on persisted History (and later opportunities if durable per-user).  
4. Optional RLS in Supabase for defense in depth.  
5. Optional BFF later for cookie sessions — engines unchanged.  
6. If a custom domain is purchased later, Cloudflare Access can become an **additional** edge layer — not a rewrite of analysis code.

---

## 10. Confirmation — no changes made

No source, dependency, database, migration, Cloudflare, Vercel, Render, staging, commit, push, or deployment changes were performed in this phase.

---

## Final status

**READY FOR ARCHITECTURE APPROVAL**

**Summary decision under free-domain constraints:**

- **Reject** Cloudflare Access as the primary control for `*.vercel.app` / `*.onrender.com`.  
- **Approve direction:** Application-level **user JWT** auth (preferably **Supabase Auth**) on FastAPI for REST + WebSocket, with production docs disabled and strict CORS.  
- Treat Vercel BFF as optional REST hardening, **not** a WebSocket solution.  
- Proceed to implementation only after explicit approval; run local then deployed PoC against the acceptance criteria above.

**STOP.** Await architecture approval.
