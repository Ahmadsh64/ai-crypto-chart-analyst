# Supabase JWT Compatibility Fix Report

**Date:** 2026-11-21
**Status:** VALIDATED — awaiting commit/push approval (no commit/push/deploy performed)

## Problem

Supabase dashboard confirms:

- **Current** signing key: ECC P-256 → **ES256**
- **Previously used** signing key: **HS256** (shared secret)

The backend previously verified **HS256 only** with `SUPABASE_JWT_SECRET`, which cannot validate current ES256 access tokens.

## Solution

| Token `alg` | Verification |
|-------------|--------------|
| **ES256** | Local verify using JWKS at `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`, key selected by JWT `kid` |
| **HS256** | Remote verify via `GET {SUPABASE_URL}/auth/v1/user` with `Authorization: Bearer` + `apikey: SUPABASE_ANON_KEY` — **no trust of unverified JWT claims** |
| Other / `none` | Rejected |

Enforced for ES256: algorithm allowlist (`ES256` only), `iss` = `{SUPABASE_URL}/auth/v1`, `aud` = `authenticated`, `exp`, `sub`, email allowlist.
Enforced for HS256: Auth-server acceptance, then email/`id` from Auth response + allowlist.
JWKS: in-process cache TTL 600s; unknown `kid` forces one refresh; fetch failures are not sticky.

## Exact changed files

| Path | Change |
|------|--------|
| `backend/app/core/security.py` | ES256 JWKS + remote HS256 verification |
| `backend/app/core/config.py` | `supabase_anon_key`, issuer/JWKS URL helpers |
| `backend/app/main.py` | Startup misconfig check updated |
| `backend/requirements.txt` | `cryptography==44.0.0` (required for ES256) |
| `backend/tests/test_auth.py` | Expanded auth matrix |
| `.env.example` | Document `SUPABASE_ANON_KEY`; JWT secret optional |
| `render.yaml` | Prefer `SUPABASE_ANON_KEY` over JWT secret |
| `docs/FINAL_RELEASE_READINESS_REPORT.md` | Updated for this fix |
| `docs/FINAL_DEPLOYMENT_GUIDE.md` | Auth env / architecture notes corrected |
| `docs/SUPABASE_JWT_COMPATIBILITY_FIX_REPORT.md` | This report |

**Not modified:** SMC/ICT engines, scanner algorithms, AI analysis, trade plan / TP-SL logic, Alembic migrations, frontend auth UI (unchanged for this fix).

## Clean dependency validation (isolated Python 3.12.10)

| Check | Result |
|-------|--------|
| Python | **3.12.10** (clean venv `.venv-jwt-validate`, removed after run) |
| `pip install -r requirements.txt` | **PASS** — complete install succeeded |
| `cryptography==44.0.0` | **PASS** — installed from requirements |
| ES256 imports (`cryptography` EC + `jwt.algorithms.ECAlgorithm`) | **PASS** |
| `from app.main import app` | **PASS** (84 routes) |
| `pip check` | **PASS** — `No broken requirements found.` |
| Auth tests | **PASS** — 22 passed |
| Full backend suite | **PASS** — **520 passed, 6 skipped** |

Note: clean-venv full suite reported 520/6 vs earlier working-venv 522/4; difference is additional skips only (no failures). Dependency versions were not modified during validation.

## Security / Git review

| Check | Result |
|-------|--------|
| Secrets / JWT values / private keys in diff | **None** (`.env.example` empty placeholders only; docs mention `service_role` as forbidden) |
| `.env` / `backend/.env` | **Ignored**, not staged |
| Trading / SMC / ICT / scanner algorithm / AI analysis logic | **Unchanged** |
| Intended files only | **Yes** (list above) |
| Previous release commit intact | **Yes** — `HEAD` / `origin/main` = `858a3a0` (working tree has uncommitted fix only) |

## Git status (after validation; no commit)

```
## main...origin/main
 M .env.example
 M backend/app/core/config.py
 M backend/app/core/security.py
 M backend/app/main.py
 M backend/requirements.txt
 M backend/tests/test_auth.py
 M docs/FINAL_DEPLOYMENT_GUIDE.md
 M docs/FINAL_RELEASE_READINESS_REPORT.md
 M render.yaml
?? docs/SUPABASE_JWT_COMPATIBILITY_FIX_REPORT.md
(+ local-only untracked audit scripts / qa-artifacts — not part of this fix)
```

## Operator env (Render)

Required when `AUTH_ENABLED=true`:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY` (anon/publishable; same value as frontend public key is OK)
- `AUTH_ALLOWED_EMAILS`

`SUPABASE_JWT_SECRET` is **not** required for verification anymore.

## Remaining limitations

1. Not committed/pushed yet — awaiting approval.
2. Real Supabase E2E with live ES256 tokens still needed after deploy.
3. WebSocket still passes access token in query string (known personal-beta log risk).
4. JWKS/Auth HTTP dependency: outages → fail closed (503 for provider errors).
5. No Supabase signing-key rotation was performed (by design).

## Confirmation

- Clean install + `pip check` + full tests completed in isolated Python **3.12.10**.
- No trading/SMC/scanner/AI logic changes.
- No migrations / deploy / commit / push / production database operations.
- No secrets printed.
- Temporary validation venv removed after use.
