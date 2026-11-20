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
| `analysis/ict` | Sessions, PDH/PDL, OTE, kill zones |
| `analysis/decision_engine` | LONG / SHORT / WAIT / NO TRADE scoring |
| `analysis/trade_plan` | Entry, SL, TP1–3, position sizing |
| `replay/` | Historical multi-TF replay clock (Phase 5.1) |
| `replay/analysis/` | Historical analysis pipeline on replay prefixes (Phase 5.2.1) |
| `ai/` | Vision + explanation with Pydantic validation |
| `backtesting/` | Historical simulation without look-ahead (later) |
| `database/` | SQLAlchemy models, Alembic, repositories |

## Analysis modes

- **Mode A — Live Market:** OHLCV from exchange → indicators/SMC/ICT → decision → trade plan → AI explanation.
- **Mode B — Screenshot:** Vision interprets visible chart → cross-check with exchange data when symbol/TF/time known → never invent prices.

## Market types (never mixed)

- Binance Spot
- Binance USDT-M Futures
- Bybit Spot
- Bybit Linear Perpetual

## Phase map

1. Scaffold, health API, dashboard shell  
2. Exchange OHLCV + charts  
2.5. Real-time `/ws/market` (Binance + Bybit)  
3.1. Technical indicators engine + Chart Analyzer panel — see [indicators.md](indicators.md)  
3.2. Market Structure engine (swings / BOS / CHoCH / MSS) — see [strategy_definitions.md](strategy_definitions.md)  
3.3. Liquidity engine (EQH/EQL / BSL/SSL / sweeps) — see [liquidity_definitions.md](liquidity_definitions.md)  
3.4. Order Blocks & FVG — see [ob_fvg_definitions.md](ob_fvg_definitions.md)  
4.1. Multi-Timeframe data orchestration — see [multi_timeframe_architecture.md](multi_timeframe_architecture.md)  
4.2. Deterministic confluence scoring — see [confluence_engine.md](confluence_engine.md)  
4.3. Trade plan engine — see [trade_plan_engine.md](trade_plan_engine.md)  
4.4. Final decision engine — see [final_decision_engine.md](final_decision_engine.md)  
5.1. Historical replay engine — see [PHASE_5_1_HISTORICAL_REPLAY.md](PHASE_5_1_HISTORICAL_REPLAY.md)  
5.2.1. Historical analysis pipeline (**current**) — see [PHASE_5_2_1_HISTORICAL_ANALYSIS.md](PHASE_5_2_1_HISTORICAL_ANALYSIS.md)  
5.2.2+. Simulated fills / P&L (not started)  
5. OpenAI vision + explanation  
6. PostgreSQL, journal, analytics  
7. Docker polish, full QA  

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
