# AI Crypto Chart Analyst

Professional AI-powered cryptocurrency chart analysis platform combining Smart Money Concepts (SMC), ICT, technical indicators, multi-timeframe confluence, Binance/Bybit market data, vision chart analysis, risk management, and historical backtesting.

> Analysis-only. The first release does **not** execute real trades.

## Current status (Phase 5.4.0 complete — with limitations; Phase 6.0.1 / 6.0.1.1 design complete)

- Monorepo structure (`frontend/`, `backend/`, `docs/`, `infra/`)
- FastAPI health + market REST APIs
- Binance / Bybit public REST OHLCV + tickers
- **Real-time WebSocket hub** at `/ws/market` (Binance + Bybit streams)
- Incremental Lightweight Charts candle updates (no full reload per tick)
- Overview / Live Market prices update via WebSocket (REST used as historical seed)
- **Technical Indicators Engine** (EMA/SMA, RSI, MACD, Stoch RSI, ATR, Bollinger, volume)
- **Market Structure Engine** (swings, HH/HL/LH/LL, BOS, CHoCH, MSS)
- **Liquidity Engine** (EQH/EQL, BSL/SSL, sweeps) — see `docs/liquidity_definitions.md`
- **Order Blocks & Fair Value Gaps** — see `docs/ob_fvg_definitions.md`
- **Multi-Timeframe orchestration** — see `docs/multi_timeframe_architecture.md`
- **Confluence scoring** (preliminary assessment only) — see `docs/confluence_engine.md`
- **Trade Plan engine** (hypothetical entry/SL/TP/RR/sizing) — see `docs/trade_plan_engine.md`
- **Final Decision engine** (`LONG` / `SHORT` / `WAIT` / `NO TRADE`) — see `docs/final_decision_engine.md`
- `GET /api/v1/...` includes `multi-timeframe` + `confluence` + `trade-plan` + `decision`
- Live updates include `multi_timeframe_update` / `confluence_update` / `trade_plan_update` / `decision_update`
- Chart Analyzer: MTF + Confluence + Trade Plan + Final Decision panels
- **Phase 5.4.0 AI Vision & Analysis Orchestration** — Analyze button, vision upload, explainer + compare (`POST /api/v1/ai/*`); see `docs/PHASE_5_4_0_AI_VISION_ANALYSIS_ORCHESTRATION.md`. Live OpenAI provider success requires `OPENAI_API_KEY` (otherwise `AI_UNAVAILABLE` with deterministic engines preserved).
- **Phase 6.0.1 / 6.0.1.1 Database Architecture (design only)** — PostgreSQL persistence plan with event idempotency, `analysis_run_id` consistency, and financial reconstruction rules; no DB installed yet. See `docs/PHASE_6_0_1_DATABASE_ARCHITECTURE.md`.

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

See [docs/architecture.md](docs/architecture.md) for Phases 2–7.
