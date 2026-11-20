# Setup Guide (Windows + PowerShell)

## Prerequisites

- Node.js 20+ (tested with 22)
- Python 3.12+ (tested with 3.13)
- PowerShell 5+ / Windows Terminal
- Optional later: Docker Desktop, PostgreSQL 16

## 1. Clone / open the repo

```powershell
cd "C:\Users\admin\OneDrive\שולחן העבודה\עבודה\ai-crypto-chart-analyst"
```

## 2. Environment files

```powershell
Copy-Item .env.example .env
Copy-Item .env.example frontend\.env.local
```

Edit `frontend\.env.local` so it contains at least:

```
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_APP_NAME=AI Crypto Chart Analyst
```

## 3. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health check: http://127.0.0.1:8000/api/v1/health  
Swagger: http://127.0.0.1:8000/docs

## 4. Frontend (new terminal)

```powershell
cd frontend
npm install
npm run dev
```

App: http://localhost:3000 (redirects to `/dashboard`)

## 5. Tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest -q
```

## Notes

- Phase 1 does not require PostgreSQL, Redis, or OpenAI keys.
- Never put `OPENAI_API_KEY` in any `NEXT_PUBLIC_*` variable.
- Analysis-only: the platform never places exchange orders.
