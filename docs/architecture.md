# Architecture — AI Crypto Chart Analyst

## Overview

Monorepo with a Next.js App Router frontend and a FastAPI Python backend. Numerical trading calculations are always produced by deterministic Python engines. AI layers explain and interpret — they never invent prices or indicator values.

```
┌────────────────────┐         REST / WS          ┌──────────────────────────┐
│  Next.js Frontend  │ ◄────────────────────────► │  FastAPI Backend         │
│  Tailwind · Zustand│                            │  Analysis · Exchanges    │
│  Lightweight Charts│                            │  AI Vision / Explainer   │
└────────────────────┘                            └────────────┬─────────────┘
                                                               │
                     ┌──────────────┬──────────────────────────┼──────────────┐
                     ▼              ▼                          ▼              ▼
               Binance API    Bybit API                  PostgreSQL        OpenAI
               (public MD)    (public MD)                (Phase 6)         (Phase 5)
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| `exchanges/` | Binance & Bybit adapters, normalized OHLCV |
| `market_data/` | Candle store helpers, WebSocket manager |
| `analysis/indicators` | Deterministic EMA/SMA, RSI, MACD, Stoch RSI, ATR, Bollinger, volume (Phase 3.1) |
| `analysis/market_structure` | Swings, HH/HL/LH/LL, BOS, CHoCH, MSS (Phase 3.2) |
| `analysis/liquidity` | EQH/EQL, BSL/SSL, sweeps (Phase 3.3) |
| `analysis/ob_fvg` | Order Blocks, Fair Value Gaps (Phase 3.4) |
| `analysis/multi_timeframe` | 4H/1H/15M/5M data orchestration (Phase 4.1) |
| `analysis/confluence` | Deterministic confluence scoring (Phase 4.2) |
| `analysis/decision_engine` | LONG / SHORT / WAIT / NO TRADE scoring (Phase 4.4) |
| `analysis/trade_plan` | Entry, SL, TP1–3, position sizing (Phase 4.3) |
| `analysis/ict`, `analysis/smc` | Reserved empty — ICT sessions not started; SMC lives in structure/liquidity/ob_fvg |
| `replay/` | Historical multi-TF replay + sim/costs/analytics (Phase 5.1–5.2.x) |
| `scanner/` | Market Opportunities scanner (Phase 5.5) |
| `ai/` | Vision + explanation with Pydantic validation (Phase 5.4) |
| `db/` | SQLAlchemy / Alembic persistence (Phase 6.0.2+) |
| `backtesting/`, `database/` | Unused shells — use `replay/` and `db/` |

## Analysis modes

- **Mode A — Live Market:** OHLCV from exchange → indicators/SMC/ICT → decision → trade plan → AI explanation.
- **Mode B — Screenshot:** Vision interprets visible chart → cross-check with exchange data when symbol/TF/time known → never invent prices.

## Market types (never mixed)

- Binance Spot
- Binance USDT-M Futures
- Bybit Spot
- Bybit Linear Perpetual

## Phase map

Living detail: **[STATUS.md](STATUS.md)**.

1. Scaffold, health API, dashboard shell — **shipped**  
2. Exchange OHLCV + charts — **shipped**  
2.5. Real-time `/ws/market` (Binance + Bybit) — **shipped**  
3.1–3.4. Indicators, structure, liquidity, OB/FVG — **shipped**  
4.1–4.4. MTF, confluence, trade plan, decision — **shipped**  
5.1–5.2.x. Historical replay + sim/costs/analytics/reporting — **shipped** (`replay/`)  
5.3 / 5.3.1. Trade-plan chart visualization + monitoring — **shipped**  
5.4.x. AI vision + AI Market Analyzer — **shipped**  
5.5. Market Opportunities scanner MVP — **shipped**  
6.0.2–6.0.3.1. DB foundation, Analyze soft-persist, History UI — **shipped** (`db/`)  
6.0.4. Replay persistence — **not started**  
6.0.5–6.0.6. Journal / standalone performance — **not started**  
7. Docker polish, full QA — **not started**  
ICT sessions / kill zones — **not started** (reserved) 

## Indicators / structure realtime path

```
Exchange candle WS → StreamManager → WebsocketManager
                                 ↘ IndicatorRuntime → indicator_update
                                 ↘ StructureRuntime → structure_update
                                 ↘ LiquidityRuntime → liquidity_update
                                 ↘ ObFvgRuntime → ob_fvg_update
                                 ↘ MultiTimeframeRuntime → multi_timeframe_update
                                 ↘ ConfluenceRuntime → confluence_update
```

No per-feature exchange sockets. Structure/liquidity/OB-FVG events emit only when closed candles confirm; deterministic `event_key`s prevent duplicates. MTF may subscribe multiple kline intervals on the same exchange connection. Confluence recomputes only on confirmed ladder candle closes.
