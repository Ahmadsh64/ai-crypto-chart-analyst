# Final Pre-Push Security Check

**Date:** 2026-11-21  
**Scope:** READ-ONLY review (JWT verification, WebSocket token handling, Git release contents)  
**Staging:** empty (nothing staged or unstaged by this review)  
**Secrets:** none printed or requested

---

## 1. JWT verification verdict

**Verdict: COMPATIBLE WITH LEGACY SUPABASE JWT SECRET (HS256) ONLY — NOT COMPATIBLE WITH DEFAULT ASYMMETRIC SIGNING KEYS**

### What the code does (`backend/app/core/security.py`)

| Check | Status | Detail |
|-------|--------|--------|
| Supported algorithms | **HS256 only** | `jwt.decode(..., algorithms=["HS256"])` |
| Signature verification | **Yes** | Verified with `SUPABASE_JWT_SECRET` via PyJWT |
| Audience (`aud`) | **Yes** | Required; must equal `"authenticated"` |
| Expiration (`exp`) | **Yes** | Claim required; PyJWT rejects expired tokens (`InvalidTokenError` → 401) |
| Subject (`sub`) | **Yes** | Required after decode; missing → 401 |
| Email claim | **Yes** | Required; compared case-insensitively to `AUTH_ALLOWED_EMAILS` |
| Email allowlist | **Yes** | Non-allowlisted email → **403** |
| Issuer (`iss`) | **No** | Not validated |
| JWKS / ES256 / RS256 | **No** | Not implemented |
| Token logging | **No app logging of token values** | Errors use generic messages |

Invalid, expired, wrong-signature, wrong-audience, and missing-claim tokens are rejected with **401**. Wrong email → **403**. Misconfigured `AUTH_ENABLED` without secret/allowlist → **503** on REST.

### Compatibility with Supabase (2026)

Supabase documents two systems:

1. **Legacy JWT secret** — shared secret, **HS256** (still available for backward compatibility).  
2. **JWT Signing Keys** — prefers **asymmetric** algorithms (e.g. **ES256**); JWKS at `https://<project>.supabase.co/auth/v1/.well-known/jwks.json`. New projects have defaulted toward asymmetric signing since **2025-10-01**.

**This implementation matches only path (1).**

If the intended production project still signs user access tokens with the **Legacy JWT secret (HS256)**, verification is compatible.

If the project signs access tokens only with **asymmetric signing keys**, this code will reject all real tokens (fail-closed). That is safe against forgeries, but production login will not work until JWKS-based verification is added.

`iss` is not checked. Risk is low when the JWT secret is project-unique, but issuer binding is still a hardening gap.

### Pre-deploy requirement (not a code change in this review)

Before enabling `AUTH_ENABLED=true` against a live Supabase project, confirm in the Supabase dashboard that **user access tokens are HS256-signed with the Legacy JWT secret** (or that HS256 verification of those tokens remains valid). If only asymmetric keys are active, **do not rely on this build for auth** until a JWKS update is implemented.

---

## 2. WebSocket security verdict

**Verdict: ACCEPTABLE FOR PERSONAL BETA WITH KNOWN QUERY-STRING LOGGING RISK — VALIDATE-BEFORE-ACCEPT IS CORRECT**

### Current design

| Item | Finding |
|------|---------|
| Client transport | `market-websocket.ts` / `replay-websocket.ts` append `?access_token=<jwt>` |
| Server validation timing | `authenticate_websocket()` runs **before** `handle_client()` → **before** `websocket.accept()` |
| Failure path | Close with code **4401** (or 1011 if misconfigured); handler returns without accepting |
| Success path | Same JWT rules as REST (signature, aud, exp, allowlist) |
| App logs | Exception handler logs `request.url.path` only (no query). WS auth does not log the token |
| Reverse proxies / platform logs | **Risk:** access logs (uvicorn default, Render, CDNs) often record the **full request URI**, which can include `access_token` |
| Browser limitation | Native `WebSocket` cannot set custom `Authorization` headers reliably cross-browser; query param is the common pattern |

### Short-lived single-use ticket

A ticket can be added **without redesigning** analysis/trading/scanner logic:

1. Authenticated REST `POST /api/v1/ws-ticket` (Bearer JWT) mints a short-lived, single-use opaque ticket in process memory.  
2. Client connects with `?ticket=…` (not the Supabase JWT).  
3. Server consumes ticket, then `accept()`.

That is a **small additive** auth surface, not a major redesign. Optional alternative with less infrastructure: **first JSON auth frame** after a provisional accept (still exposes a brief unauthenticated accept window unless carefully gated).

### Simplest safe approach for this personal beta (recommendation only — no code changed)

1. **Keep** query-string JWT for now (one authorized user, WSS only).  
2. **Assume** platform access logs may retain URLs; avoid sharing log dumps; prefer short Supabase access-token TTL.  
3. **Defer** tickets / first-frame auth to a hardening pass if logs or multi-user exposure become concerns.  
4. Do **not** treat query-string JWT as ideal for multi-user SaaS.

---

## 3. Exact Git release file list

**Current state:** branch `main` tracking `origin/main`; **staged files = 0**. All candidates below are modified or untracked in the working tree.

### 3.1 Intended for the release commit (include)

**Root / deploy**

- `.env.example`
- `.gitignore`
- `README.md`
- `render.yaml`

**Backend — core & auth**

- `backend/requirements.txt`
- `backend/runtime.txt`
- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/alembic/script.py.mako`
- `backend/alembic/versions/0001_extensions.py`
- `backend/alembic/versions/0002_analysis_core.py`
- `backend/alembic/versions/0003_decisions_trade_plans.py`
- `backend/alembic/versions/0004_scanner_persistence.py`
- `backend/prod-ca-2021.crt` *(public Supabase Root CA; intentional)*
- `backend/app/main.py`
- `backend/app/core/config.py`
- `backend/app/core/security.py`
- `backend/app/api/routes/websocket.py`
- `backend/app/api/routes/ai.py`
- `backend/app/api/routes/health.py`
- `backend/app/api/routes/market.py`
- `backend/app/api/routes/history.py`
- `backend/app/api/routes/opportunities.py`
- `backend/app/api/schemas/ai.py`
- `backend/app/api/schemas/market.py`
- `backend/app/api/schemas/history.py`
- `backend/app/api/schemas/opportunities.py`
- `backend/app/ai/vision/schemas.py`
- `backend/app/ai/vision/service.py`
- `backend/app/ai/vision/recognition.py`
- `backend/app/exchanges/base.py`
- `backend/app/exchanges/binance.py`
- `backend/app/exchanges/bybit.py`
- `backend/app/exchanges/manager.py`
- `backend/app/replay/session.py`
- `backend/app/replay/simulation/lifecycle.py`
- `backend/app/replay/simulation/simulator.py`
- `backend/app/market_data/markets_cache.py`
- `backend/app/services/analysis_persistence_service.py`
- `backend/app/analysis/ict/README.md`
- `backend/app/analysis/smc/README.md`
- `backend/app/backtesting/README.md`
- `backend/app/database/README.md`
- `backend/app/db/**` *(session, SSL, models, repositories)*
- `backend/app/scanner/**`
- `backend/tests/test_auth.py`
- `backend/tests/test_alembic_ssl.py`
- `backend/tests/test_db_phase_6_0_2.py`
- `backend/tests/test_db_ssl_ca.py`
- `backend/tests/test_db_supabase_live.py`
- `backend/tests/test_phase_5_4_2_*.py`
- `backend/tests/test_phase_5_5_*.py`
- `backend/tests/test_phase_6_0_3_*.py`

**Frontend**

- All modified/untracked under `frontend/` required for the app (layouts, login, auth provider, supabase client, api/ws clients, analyzer/opportunities/history UI, `package.json`, `package-lock.json`, `vercel.json`, related `lib/` helpers and tests)

**Docs (product / deploy / phase reports — optional but consistent with prior release prep)**

- `docs/FINAL_DEPLOYMENT_GUIDE.md`
- `docs/FINAL_RELEASE_READINESS_REPORT.md`
- `docs/FINAL_PRE_PUSH_SECURITY_CHECK.md` *(this file, once present in the tree)*
- `docs/architecture.md`
- `docs/PHASE_*.md` / `docs/DEPLOYMENT_*.md` / `docs/STATUS.md` / `docs/README.md` / `docs/AI_MARKET_ANALYZER_UI_UX_SPEC.md`
- `docs/PHASE_6_0_1_MIGRATION_PLAN.md` *(modified)*

---

## 4. Excluded files

### Must exclude (secrets / credentials / private local env)

| Path | Reason |
|------|--------|
| `.env` | Local secrets — **gitignored** |
| `backend/.env` | Local secrets — **gitignored** |
| `frontend/.env.local` | Local frontend env — **gitignored** |
| `backend/prod-ca-2021 (1).crt` | Duplicate CA download — **gitignored** |
| `*.pem` / `*.key` / `credentials.json` / `service-account*.json` | Credential patterns — **gitignored** |
| `backend/.venv/`, `frontend/node_modules/`, `.cursor/` | Local/runtime — **gitignored** |

**Confirmation:** `.env`, `backend/.env`, `frontend/.env.local`, and the duplicate CA are ignored and not tracked. No private keys were found in the intended release set. `.env.example` contains **empty placeholders / localhost examples only** (no live secrets).

### Recommend exclude (not required to run the product)

| Path | Reason |
|------|--------|
| `backend/scripts/_audit_phase_551_hist.py` | Local Phase 5.5.1 audit helper |
| `backend/scripts/_audit_phase_551_live.py` | Local live audit helper |
| `docs/qa-artifacts/**` | Screenshots, fixtures, QA dumps (large; not runtime) |
| Especially `docs/qa-artifacts/phase-5-5-1/live_audit_raw.json` | Live market audit dump (not a credential, still unnecessary in release) |

### Do not use blind `git add .`

Stage explicitly (see `docs/FINAL_DEPLOYMENT_GUIDE.md` §3), then `git status` before commit.

---

## 5. Remaining risks

1. **JWT algorithm mismatch** with asymmetric-default Supabase projects → auth fails closed until JWKS support or Legacy HS256 confirmed.  
2. **No `iss` validation** on JWTs.  
3. **WebSocket access tokens in query strings** may appear in reverse-proxy / platform access logs.  
4. **`AUTH_ENABLED` defaults to `false`** — production Render must set `true` or the API stays open.  
5. **`GET /api/v1/health` remains public** (intentional for Render probes; low sensitivity).  
6. **Free Render spin-down** and in-memory scanner state are operational risks, not secret-leak risks.  
7. **`origin/main` is outdated** until this working tree is committed and pushed — deploying GitHub without this commit ships unauthenticated older code.

---

## 6. Final recommendation

### APPROVE COMMIT/PUSH

**Conditions (operator, not code changes in this review):**

1. Stage only the **intended** list; **exclude** secrets, duplicate CA, audit scripts, and preferably `docs/qa-artifacts/**`.  
2. After push, **before** production `AUTH_ENABLED=true`, confirm the Supabase project signs user access tokens with the **Legacy JWT secret (HS256)** — or schedule JWKS/ES256 support before go-live.  
3. Treat WebSocket query tokens as **accepted personal-beta risk**; harden later if needed.

**Do not BLOCK** the commit/push for secret leakage: none found in the intended release set.  
**Do BLOCK deploy-with-auth** against an asymmetric-only Supabase project until verification strategy matches.

---

## Confirmation

- No source, dependency, env, DB, Git staging, commit, push, or cloud configuration changes were made by this check beyond writing this report file as requested.  
- No secret values were generated, requested, or printed.
