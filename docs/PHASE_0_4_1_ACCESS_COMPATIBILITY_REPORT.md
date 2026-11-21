# Phase 0.4.1 — Cloudflare Access Compatibility Verification

**Mode:** Read-only (no code, Cloudflare, Vercel, Render, Git, or dependency changes)  
**Date:** 2026-11-21  
**Inputs:** Phase 0.4 architecture proposal + actual repository clients  
**Sources of truth:** Application source + [Cloudflare Access authorization cookie](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/) + [Access CORS docs](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/cors/)

Classification legend used below:

| Label | Meaning |
|-------|---------|
| **COMPATIBLE** | Works with current code and documented Access behavior |
| **COMPATIBLE WITH REQUIRED CONFIGURATION** | Documented as workable after Access/CORS/domain/ops settings (and possibly small approved frontend credential change) |
| **NOT COMPATIBLE** | Conflicts with current code or documented Access constraints |
| **NOT VERIFIED** | Cannot be confirmed without a live Access PoC |

---

## 1. Actual frontend/backend communication findings

### 1.1 API client

| Item | Actual behavior | Location |
|------|-----------------|----------|
| Client | Native `fetch` (no Axios) | `frontend/services/api.ts` |
| Base URL | `process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"` | `api.ts` L59 |
| Credentials | **Not set** — browser default `credentials: "same-origin"` | `request()` L83–91; vision/multipart fetches L355–360, L404–409; report downloads L693+ |
| Custom auth headers | **None** (no `Authorization`, no `X-API-Key`) | Same |
| Default JSON header | Always sets `Content-Type: application/json` on `request()` | L86–88 |
| Multipart uploads | `FormData` without manual Content-Type | `aiVisionAnalyze`, `aiAnalyzeWithVision` |
| Cache | `cache: "no-store"` | `request()` and upload helpers |
| BFF / Route Handlers | **Absent** | no `frontend/app/api/**` |

### 1.2 CORS preflight triggers (current code)

Cross-origin browser calls from Vercel → Render will preflight when:

- Method is not simple **GET/HEAD/POST**, or  
- Headers are non-simple — **`Content-Type: application/json` is non-simple** → **almost all `request()` calls trigger OPTIONS**, or  
- Credentialed cross-origin requests (once `credentials: "include"` is added).

Multipart POSTs are also cross-origin non-simple in practice and typically preflight.

**Backend today:** FastAPI `CORSMiddleware` allows configured origins, methods `*`, headers `*`, `allow_credentials=True` (`backend/app/main.py`). That satisfies origin CORS **after** Access lets the request through — it does **not** authenticate.

### 1.3 WebSockets

| Item | Actual behavior | Location |
|------|-----------------|----------|
| Market URL | Derive from `NEXT_PUBLIC_API_URL`; `https`→`wss`, path `/ws/market` | `market-websocket.ts` `wsUrl()` L110–117 |
| Replay URL | Same pattern; path `/ws/replay` | `replay-websocket.ts` L5–12 |
| Constructor | `new WebSocket(url)` — **no** protocols, **no** query token, **no** custom headers | L156; L27 |
| Auth | **None** | Backend `websocket.py` accepts clients without credentials |
| Lifecycle | Connect / heartbeat / exponential reconnect on close | `MarketWebsocketClient` |
| Subprotocol auth | Not used | — |

Browser WebSocket upgrade **can** send cookies for the API host automatically; the app does not add any other auth.

### 1.4 Dashboard endpoints used (via `api` object)

Representative surface (not exhaustive of every replay sub-route):

- Health / market: `/api/v1/health`, `/exchanges`, `/markets`, `/market/candles`, `/market/ticker`
- Engines: `/indicators`, `/market-structure`, `/liquidity`, `/ob-fvg`, `/multi-timeframe`, `/confluence`, `/trade-plan`, `/decision`
- AI: `/ai/analyze`, `/ai/vision/analyze`, `/ai/analyze-with-vision`, `/ai/compare`
- History: `/history/analyses`, by-run detail
- Opportunities: list, `/opportunities/status`, **`POST /opportunities/scan`**
- Replay: large session/control/report/export surface under `/api/v1/replay/...`
- WS: `/ws/market`, `/ws/replay`

### 1.5 Error handling for 302 / 401 / 403 / CORS

| Condition | Actual handling |
|-----------|-----------------|
| Non-OK HTTP | `ApiError` with `status` + parsed `detail` (`api.ts` L93–101) |
| Specific 401/403 UX | **No** dedicated login redirect / Access handling |
| HTTP 302 HTML login page | Treated as failure; `response.json()` often fails → generic statusText |
| CORS failure | Browser blocks; fetch rejects; UI shows generic failure strings |
| WS auth failure / Access challenge | `onclose` / reconnect loop — **no** Access-aware recovery |

---

## 2. REST and CORS compatibility analysis

### Scenario matrix

| ID | Scenario | Classification | Basis |
|----|----------|----------------|-------|
| A | One Access application covering both Vercel + Render hostnames | **COMPATIBLE WITH REQUIRED CONFIGURATION** | Access supports multiple app hostnames / policies; still two origins for CORS. Documented cookie is **per application domain**. |
| B | Separate Access apps, same authorized email | **COMPATIBLE WITH REQUIRED CONFIGURATION** | Documented: team-domain SSO cookie reduces re-login; each app still needs its own `CF_Authorization` application cookie after first visit ([authorization cookie docs](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/)). |
| C | Browser REST with Access cookies | **NOT COMPATIBLE** *as current code* → **COMPATIBLE WITH REQUIRED CONFIGURATION** after change | CF docs require `credentials: "include"` for cross-origin Access cookie auth. Current `fetch` omits it → cookies **not** sent cross-origin. |
| D | CORS preflight OPTIONS | **COMPATIBLE WITH REQUIRED CONFIGURATION** | CF docs: OPTIONS have **no cookies** → Access returns **403** unless “Bypass OPTIONS requests to origin” **or** Access answers preflight with matching CORS headers. Only OPTIONS may be bypassed; actual GET/POST/WS must stay authenticated. Origin FastAPI already enforces CORS. |
| E | Credentialed cross-origin requests | **COMPATIBLE WITH REQUIRED CONFIGURATION** | Needs `credentials: "include"` + `Access-Control-Allow-Credentials: true` + explicit origin (not `*`). Backend already `allow_credentials=True` with explicit origin list. |
| H | Access login redirects + SPA | **COMPATIBLE WITH REQUIRED CONFIGURATION** / **NOT VERIFIED** live | Top-level navigation to API host can complete login; XHR/fetch to unauthenticated Access often surfaces as opaque CORS errors. App has no Access-aware redirect UX. Manual “open API URL once / refresh” is CF’s documented simple-request guidance. |

**Documented vs assumption:** Cookie + OPTIONS behavior above is from Cloudflare docs. Live success with this repo’s SPA was **not** exercised in this phase → remaining residual **NOT VERIFIED** until PoC.

---

## 3. WebSocket compatibility analysis

| ID | Scenario | Classification | Basis |
|----|----------|----------------|-------|
| F | Browser WebSocket handshake auth via Access | **COMPATIBLE WITH REQUIRED CONFIGURATION** | After user has a valid `CF_Authorization` cookie for the **API host**, browsers send cookies on WS upgrade to that host. App uses standard `WebSocket` (no header injection). **No app-level WS auth exists.** Cross-site cookie delivery still subject to SameSite / third-party restrictions (scenario G). |
| — | WS without prior API-host login | **NOT COMPATIBLE** | Upgrade would hit Access challenge; JS WebSocket cannot complete interactive login redirect. |

Reconnect loops will retry blindly on Access failures — operational footgun, not a security bypass.

---

## 4. Cookie and authentication findings

| ID | Scenario | Classification | Basis |
|----|----------|----------------|-------|
| G | Third-party cookies / SameSite | **COMPATIBLE WITH REQUIRED CONFIGURATION** on **same-site custom domains**; **NOT COMPATIBLE / fragile** on default `*.vercel.app` → `*.onrender.com` | Different site registrable domains ⇒ cross-site requests. CF docs warn browsers (esp. private mode) may block third-party cookies. Application cookie SameSite is admin-configurable (None/Lax/Strict). Sibling subdomains under one apex (`app.example.com` + `api.example.com`) are **same-site**, which is far more reliable for sending the API host cookie from the UI. |
| — | Embed Access service token in frontend JS | **NOT COMPATIBLE** (forbidden by Phase 0.4 / this phase) | Tokens would be extractable; CF Worker pattern keeps service token **server-side** only. |

---

## 5. Domain and deployment requirements

| ID | Scenario | Classification | Notes |
|----|----------|----------------|-------|
| I | Vercel default + Render default hostnames | **COMPATIBLE WITH REQUIRED CONFIGURATION** but **high friction** | Possible per CF CORS docs, but cross-site cookies + double login + SPA CORS errors are likely. **PoC mandatory.** |
| I | Custom domains under one apex behind Cloudflare | **COMPATIBLE WITH REQUIRED CONFIGURATION** (recommended) | e.g. `app.<domain>` → Vercel, `api.<domain>` → Render, both proxied through Cloudflare with Access. Enables same-site cookie behavior and unified DNS/TLS. |
| — | Workers required? | **Not required** for baseline; **optional** | CF documents a Worker + service token to avoid logging into the API host separately by making REST same-origin under the UI host. That Worker must **not** expose secrets to the browser. Workers do **not** replace a proper long-lived WebSocket proxy by themselves. |

### Exact configuration requirements (next approved implementation / ops phase)

1. **Access apps:** Protect UI hostname and API hostname (one or two Access applications; same allowlisted email).  
2. **Cookies:** Ensure API application cookie can be sent on browser calls from the UI (prefer same-site custom domains; configure SameSite appropriately per CF admin options).  
3. **CORS (origin):** `CORS_ORIGINS` = exact UI origin only; keep credentials allowed.  
4. **OPTIONS:** On the Access application for the API: either **Bypass OPTIONS to origin** (only OPTIONS) **or** configure Access CORS preflight responses to match origin (Allow-Origin = UI, Allow-Credentials = true, methods/headers used by the app including `content-type`).  
5. **Frontend (future approved code change):** set `credentials: "include"` on all cross-origin `fetch` calls (JSON + multipart + downloads). WebSocket needs no code auth header if cookies work.  
6. **Do not** bypass authentication for real application methods (GET/POST/WS).  
7. **Do not** put Access Client Secret / service tokens in `NEXT_PUBLIC_*` or client bundles.  
8. **Custom domains:** Strongly recommended before calling the architecture “production-ready.”  
9. **Workers:** Optional optimization for REST same-origin; not a substitute for securing `/ws/*`.

---

## 6. Alternative architecture comparison

| Approach | REST | WebSockets | Secrets in browser? | Fit with current FE | Notes |
|----------|------|------------|---------------------|---------------------|-------|
| Access on UI + API (custom domains) + `credentials: "include"` | Strong | Strong if cookies same-site | No | Small FE change | **Best match** to current direct browser→API design |
| Access + default vercel/onrender hosts | Fragile | Fragile | No | Same + cookie risk | PoC only |
| Vercel BFF for REST + Access/JWT for WS | Strong REST | Needs separate WS auth | No (keys on Vercel server) | Larger FE rewrite | Vercel serverless **rewrites do not provide a general WebSocket upgrade proxy**; long-lived WS termination on Vercel is not the normal Next.js pattern |
| App-level user JWT (future SaaS) | Strong | JWT/ticket on connect | No | Medium | Best long-term; more build than personal beta |
| Shared API key in browser | Appears easy | Hard (no WS headers) | **Yes — reject** | Minimal | Violates constraints |

**Vercel WebSocket limitation (explicit):** A normal Vercel/Next **rewrite** to Render forwards HTTP; it is **not** a verified, supported pattern for upgrading and holding authenticated browser WebSockets through the serverless edge as a transparent BFF. Do not assume REST BFF rewrites equal WS support.

---

## 7. Final recommendation

### Recommended architecture (personal beta → SaaS-ready)

1. Put **custom domains** on Cloudflare: UI and API under the **same apex**.  
2. Cloudflare Access allowlist: **one authorized email** on **both** UI and API applications.  
3. Keep browser→API REST and WS (matches existing clients).  
4. In the **next approved implementation phase**: add `credentials: "include"` to all API `fetch` calls; tighten production CORS; disable `/docs`/`/openapi.json` in production.  
5. Configure Access CORS / OPTIONS handling so only preflight is specially handled; all real requests remain authenticated.  
6. Run a **controlled PoC** (login, REST analyze, `POST /opportunities/scan`, live `/ws/market`) before any public URL sharing.  
7. Evolve later to multi-user by replacing Access allowlist with app identity (JWT/session) at the API edge — engines unchanged.

### What is **not** ready without further work

- Declaring Access “works out of the box” with **current** `fetch` (missing credentials).  
- Relying on `*.vercel.app` → `*.onrender.com` without proving third-party cookie behavior.  
- Assuming a Vercel BFF rewrite solves WebSockets.

---

## 8. Exact implementation plan for the next approved phase

**Do not execute until approved.**

1. Ops: Cloudflare DNS + custom domains for UI/API; Access apps + email policy.  
2. Ops: Access CORS / Bypass OPTIONS (OPTIONS only) for API app.  
3. Code (approved security hardening only):  
   - `frontend/services/api.ts` — `credentials: "include"` on all fetches.  
   - Confirm multipart/download paths included.  
   - Backend: production docs disabled; `CORS_ORIGINS` = UI origin.  
4. PoC checklist: Access login UI; Access login API host once; health; analyze; scan trigger; WS ticks; private window negative test.  
5. Document SaaS follow-on: JWT middleware replacing Access for multi-user.

No scanner/SMC/AI logic, schemas, or dependency changes in that plan.

---

## 9. Confirmation — no changes made

| Change type | Done? |
|-------------|-------|
| Source / deps / DB / migrations | **No** |
| Cloudflare / Vercel / Render config | **No** |
| Git stage / commit / push / deploy | **No** |
| Phase 0 backup | **Preserved** |

---

## Final status

**VERIFIED WITH LIMITATIONS**

- Compatibility is established from **actual client code** + **Cloudflare documentation**.  
- Current repository is **not** Access-ready without a small credentialed-fetch change and careful Access/CORS/domain setup.  
- A **live Access proof-of-concept** is still required before deployment confidence.  
- Default dual-vendor hostnames without custom domains remain high-risk for cookies.

**STOP.** Await architecture / next-phase approval.
