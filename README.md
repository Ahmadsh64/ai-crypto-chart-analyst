# AI Crypto Chart Analyst

Professional AI-powered cryptocurrency chart analysis platform combining Smart Money Concepts (SMC), ICT, technical indicators, multi-timeframe confluence, Binance/Bybit market data, vision chart analysis, risk management, and historical backtesting.

> Analysis-only. The first release does **not** execute real trades.

## Current status

**Living status board:** [docs/STATUS.md](docs/STATUS.md) · **Docs index:** [docs/README.md](docs/README.md)

Shipped through **Phase 6.0.3.1** (Analyze soft-persist + History UI). **Phase 6.0.4** (Replay persistence) not started. Journal / standalone Performance deferred.

Highlights:

- Monorepo (`frontend/`, `backend/`, `docs/`, `infra/`) · FastAPI · Binance/Bybit REST + **WebSocket hub** `/ws/market`
- Phase 3 engines: indicators, structure, liquidity, OB/FVG
- Phase 4: MTF, confluence, trade plan, final decision (`LONG` / `SHORT` / `WAIT` / `NO TRADE`)
- Phase 5: historical replay stack, trade-plan chart viz, AI vision / **AI Market Analyzer**, Market Opportunities scanner (5.5 MVP)
- Phase 6.0.2–6.0.3.1: PostgreSQL foundation (`backend/app/db/`), Analyze soft-persist, `/history`
- Surfaces: Overview · Live Market · Opportunities · Analyzer · Trade Setups · SMC · History · Replay · Settings

## Quick start (Windows PowerShell)

```powershell
cd "C:\Users\admin\OneDrive\שולחן העבודה\עבודה\ai-crypto-chart-analyst"
Copy-Item .env.example .env

# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

New terminal:

```powershell
cd frontend
npm install
# Ensure NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 in .env.local
npm run dev
```

- Frontend: http://localhost:3000  
- API health: http://127.0.0.1:8000/api/v1/health  
- API docs: http://127.0.0.1:8000/docs  

Full instructions: [docs/setup_guide.md](docs/setup_guide.md)  
Status: [docs/STATUS.md](docs/STATUS.md) · Docs index: [docs/README.md](docs/README.md)  
Architecture: [docs/architecture.md](docs/architecture.md)  
Indicators: [docs/indicators.md](docs/indicators.md)

## Stack

| Area | Tech |
|------|------|
| Frontend | Next.js, TypeScript, Tailwind CSS, TanStack Query, Zustand, Zod |
| Backend | Python 3.12+, FastAPI, Pydantic, SQLAlchemy, Pandas |
| Data | Binance & Bybit public market data (Phase 2) |
| AI | OpenAI vision + structured explanations (Phase 5) |
| DB | PostgreSQL (Phase 6) |

## Roadmap

See [docs/STATUS.md](docs/STATUS.md) for shipped vs deferred, and [docs/architecture.md](docs/architecture.md) for layer detail.
