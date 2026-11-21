# Final Deployment Guide — Personal Beta (Free Domains)

**Audience:** one authorized personal user  
**Hosting:** Vercel (frontend) + Render (backend) + Supabase PostgreSQL  
**Domains:** default `*.vercel.app` and `*.onrender.com` (no custom domain)  
**Auth:** Supabase Auth JWT validated by FastAPI (REST + WebSocket)

---

## 1. Final architecture

```
Browser
  │  login (email/password) via Supabase Auth (anon key, public)
  │  REST:  Authorization: Bearer <access_token>
  │  WS:    wss://<render>/ws/*?access_token=<access_token>
  ▼
Vercel  (Next.js, Root Directory = frontend)
  │  NEXT_PUBLIC_API_URL → Render origin
  │  NEXT_PUBLIC_SUPABASE_URL / ANON_KEY only
  ▼
Render Web Service  (rootDir = backend)
  │  AUTH_ENABLED=true → JWT verify (SUPABASE_JWT_SECRET) + AUTH_ALLOWED_EMAILS
  │  CORS_ORIGINS = exact Vercel origin (not authentication)
  │  /docs /redoc /openapi.json disabled in production
  │  GET /api/v1/health public (Render health check)
  ▼
Supabase
  ├── Auth (user accounts)
  └── PostgreSQL (Alembic 0001→0004, TLS CA verified)
```

Secrets (`SUPABASE_JWT_SECRET`, `DATABASE_URL`, `OPENAI_API_KEY`, service role) stay on Render only.

---

## 2. Exact files changed (this preparation pass)

### Auth / security / deploy config (this pass)

| Path | Change |
|------|--------|
| `backend/app/core/security.py` | Supabase JWT verify, REST dependency, WS auth |
| `backend/app/core/config.py` | `AUTH_*`, `SUPABASE_JWT_SECRET`, docs flag |
| `backend/app/main.py` | Protect routers; disable docs in production |
| `backend/app/api/routes/websocket.py` | Auth before market/replay WS |
| `backend/requirements.txt` | `PyJWT==2.10.1` |
| `backend/tests/test_auth.py` | Auth acceptance tests |
| `backend/runtime.txt` | `python-3.12.10` (already prepared) |
| `render.yaml` | Render blueprint |
| `.env.example` | Auth + Supabase public vars (names only) |
| `.gitignore` | Exclude duplicate CA / accidental nested frontend |
| `frontend/package.json` / lock | `@supabase/supabase-js` |
| `frontend/lib/supabase/client.ts` | Browser client (anon only) |
| `frontend/components/providers/auth-provider.tsx` | Session provider |
| `frontend/components/auth/require-auth.tsx` | App route gate |
| `frontend/app/login/page.tsx` | Login UI |
| `frontend/app/layout.tsx` | Wrap AuthProvider |
| `frontend/app/(app)/layout.tsx` | RequireAuth |
| `frontend/components/layout/sidebar.tsx` | Sign out |
| `frontend/services/api.ts` | Bearer on all fetches |
| `frontend/services/market-websocket.ts` | `access_token` query |
| `frontend/services/replay-websocket.ts` | `access_token` query |
| `frontend/vercel.json` | Next.js build settings |
| `docs/FINAL_DEPLOYMENT_GUIDE.md` | This guide |
| `docs/FINAL_RELEASE_READINESS_REPORT.md` | Readiness report |

### Also part of the release tree (prior local work not on `origin/main`)

Uncommitted Phase 5.4.2–6.0.3 application code, Alembic `0001`–`0004`, scanner, history UI, persistence, TLS CA `backend/prod-ca-2021.crt`, and related docs/tests. **`origin/main` is outdated until you commit and push the release list below.**

---

## 3. Exact GitHub release commands

**Do not run until you have reviewed the release summary.**

From the repository root (PowerShell):

```powershell
# 1) Confirm branch and that you will NOT add secrets
git status -sb
git check-ignore -v .env backend/.env 2>$null

# 2) Stage deliberately (never: git add .)
git add `
  .env.example .gitignore README.md render.yaml `
  backend/alembic.ini backend/alembic backend/runtime.txt backend/requirements.txt `
  backend/prod-ca-2021.crt `
  backend/app backend/tests `
  backend/scripts/_audit_phase_551_hist.py backend/scripts/_audit_phase_551_live.py `
  frontend `
  docs

# 3) Explicitly ensure secrets / junk stay out
git reset HEAD -- .env backend/.env "backend/prod-ca-2021 (1).crt" 2>$null
git status

# 4) Commit (after you approve the message)
git commit -m "$(cat <<'EOF'
Release personal beta: Phase 5.5–6.0.3 stack with Supabase Auth gate.

Protect REST and WebSockets with owner-email JWT allowlisting, disable production OpenAPI, and add Render/Vercel deployment configuration for free-domain hosting.
EOF
)"

# 5) Push only after commit review
git push -u origin HEAD
```

If `cat <<'EOF'` is awkward in Windows PowerShell, use:

```powershell
git commit -m "Release personal beta: Phase 5.5-6.0.3 stack with Supabase Auth gate."
```

**Exclude from commit:** `.env`, `backend/.env`, `backend/prod-ca-2021 (1).crt`, `.venv`, `node_modules`, `.cursor/`, any private keys.

---

## 4. Supabase setup and migration instructions

### 4.1 Project setup (dashboard)

1. Create/use a Supabase project.
2. **Authentication → Users:** create **one** user with your owner email + password.
3. **Authentication → URL configuration:** add your Vercel origin (`https://<app>.vercel.app`) to allowed redirect URLs if you later enable magic links (password login works without redirects).
4. **Project Settings → API:** copy Project URL, `anon` `public` key, and **JWT Secret** (Settings → API → JWT Settings).  
   Never put the JWT secret or service-role key in `NEXT_PUBLIC_*`.
5. **Database → Connection string:** use the **URI** suitable for the app (prefer Session pooler or direct, matching prior TLS-validated setup). Convert to `postgresql+asyncpg://…` for `DATABASE_URL`.

### 4.2 TLS

- Keep `SUPABASE_SSL_CA_FILE=prod-ca-2021.crt` (file at `backend/prod-ca-2021.crt`).
- Do **not** disable certificate verification.

### 4.3 One-time migration (after you approve production DB credentials)

On a trusted machine with `DATABASE_URL` / SSL configured (never print the URL):

```powershell
cd backend
# Ensure PERSISTENCE-related env is loaded for Alembic (same Settings as the app)
.\.venv\Scripts\python.exe -m alembic heads
# Expect: 0004_scanner_persistence (head)
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Do **not** run migrations until the production connection is configured and you explicitly approve.

---

## 5. Render dashboard settings

| Setting | Value |
|---------|--------|
| Service type | Web Service |
| Root Directory | `backend` |
| Runtime | Python (honors `runtime.txt` → 3.12.10) |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/v1/health` |
| Plan | Free (spins down when idle — expect cold starts) |

Optional: connect `render.yaml` blueprint, then fill secrets in the dashboard.

**CORS_ORIGINS** must be the exact Vercel URL, e.g. `https://ai-crypto-chart-analyst.vercel.app` (no trailing slash).

---

## 6. Vercel dashboard settings

| Setting | Value |
|---------|--------|
| Root Directory | `frontend` |
| Framework Preset | Next.js |
| Build Command | `npm run build` (default) |
| Install Command | `npm install` |
| Output | Next default (no static export) |
| Node | 20.x recommended |

Set Production environment variables (section 7). Redeploy after Render URL is known so `NEXT_PUBLIC_API_URL` is correct.

---

## 7. Environment variable table

### Backend / Render (server-only)

| Variable | Secret? | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | No | `production` |
| `DEBUG` | No | `false` |
| `HOST` | No | `0.0.0.0` |
| `PORT` | No | Provided by Render — do not hardcode |
| `CORS_ORIGINS` | No | Exact Vercel HTTPS origin |
| `AUTH_ENABLED` | No | `true` in production |
| `AUTH_ALLOWED_EMAILS` | **Yes (PII)** | Owner email allowlist (comma-separated) |
| `SUPABASE_URL` | No | Project URL |
| `SUPABASE_JWT_SECRET` | **Yes** | JWT secret for HS256 verification |
| `DATABASE_URL` | **Yes** | `postgresql+asyncpg://…` |
| `PERSISTENCE_ENABLED` | No | `true` when DB ready |
| `SUPABASE_SSL_CA_FILE` | No | `prod-ca-2021.crt` |
| `OPENAI_API_KEY` | **Yes** | Vision/explainer |
| `DOCS_ENABLED` | No | `false` (or omit; production disables docs) |
| `OPENAI_MODEL` / vision / explainer | No | Defaults ok |

### Frontend / Vercel (browser-visible if `NEXT_PUBLIC_`)

| Variable | Secret? | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | No | `https://<service>.onrender.com` (no path) |
| `NEXT_PUBLIC_APP_NAME` | No | Display name |
| `NEXT_PUBLIC_SUPABASE_URL` | No | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | **Public-by-design** | Anon key only — never service role |

### Never set on Vercel / never `NEXT_PUBLIC_`

- `SUPABASE_JWT_SECRET`
- `DATABASE_URL` / DB passwords
- `OPENAI_API_KEY`
- Supabase **service_role** key

---

## 8. Authentication setup instructions

1. Create the owner user in Supabase Auth (email + password).
2. Set Render `AUTH_ALLOWED_EMAILS` to that exact email.
3. Set Render `SUPABASE_JWT_SECRET` and `AUTH_ENABLED=true`.
4. Set Vercel `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
5. Open the Vercel app → `/login` → sign in.
6. Confirm REST calls send `Authorization: Bearer …` and WS URLs include `access_token`.

Backend allowlist is authoritative: other Supabase users receive **403** even with valid tokens.

---

## 9. Deployment order

1. **Prepare Git release** (section 3) — commit + push when you approve.  
2. **Supabase:** user + JWT secret + DB URL; run `alembic upgrade head` after approval.  
3. **Render:** create Web Service from `backend`, set env vars, deploy, note the `*.onrender.com` URL, confirm `/api/v1/health`.  
4. **Vercel:** Root Directory `frontend`, set env including `NEXT_PUBLIC_API_URL` to the Render URL, deploy.  
5. **Tighten CORS** on Render to the final Vercel origin; redeploy Render if needed.  
6. **Smoke tests** (section 10).

---

## 10. Post-deployment smoke tests

1. Anonymous `GET https://<render>/api/v1/health` → **200**.  
2. Anonymous `GET https://<render>/api/v1/opportunities/status` → **401**.  
3. Anonymous `POST https://<render>/api/v1/opportunities/scan` → **401**.  
4. `GET https://<render>/docs` → **404** in production.  
5. Browser: login with owner email → dashboard loads.  
6. Trigger Analyze / History / Opportunities with network tab showing Bearer header → **200**.  
7. Manual scan as logged-in owner → succeeds (or busy) — not 401.  
8. Live market WebSocket connects (`wss://…/ws/market?access_token=…`).  
9. Private/incognito without login cannot use API.  
10. Confirm no JWT secret / DB URL / service role in frontend bundle or Vercel public env.

---

## 11. Troubleshooting common failures

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| CORS errors in browser | `CORS_ORIGINS` mismatch | Exact Vercel origin, https, no trailing slash |
| 401 on all API calls after login | Wrong JWT secret or clock skew | Copy JWT secret from same Supabase project; check system time |
| 403 after login | Email not in `AUTH_ALLOWED_EMAILS` | Match email case-insensitively; update Render env |
| WS connects then drops / fails | Missing `access_token` on WS URL | Ensure frontend built with Supabase session; redeploy Vercel |
| Render health failing | Wrong health path / app crash | Use `/api/v1/health`; check Render logs |
| Cold start / spin-down | Free Render plan | First request after idle is slow; not a code bug |
| DB / SSL errors | Bad URL or missing CA | Use asyncpg URL + `prod-ca-2021.crt` |
| OpenAPI still visible | `ENVIRONMENT` not production and `DOCS_ENABLED` true | Set `ENVIRONMENT=production` or `DOCS_ENABLED=false` |
| Migration fails | Wrong DB credentials / SSL | Fix env locally; do not disable verify |

---

## 12. Future multi-user expansion notes

- Keep analysis / scanner / SMC engines **user-agnostic**.  
- Replace single-email allowlist with roles/tenancy tables and Supabase RLS on persisted rows.  
- Attach `user_id` (`sub`) to history/opportunities when introducing multi-tenant persistence.  
- Consider refresh-token rotation policies and optional MFA in Supabase Auth.  
- Do **not** rely on CORS or Vercel rewrites for WebSocket security — keep JWT (or tickets) on `/ws/*`.  
- Scale scanner only with an explicit multi-instance design (current scanner is single-process).
