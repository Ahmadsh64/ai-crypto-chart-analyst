# Product & phase status

Single source of truth for what is shipped vs deferred. Update this file when a phase lands or a nav surface changes ownership.

Last reviewed: 2026-11-20

## Ownership (where features live)

| Job | Canonical UI | Notes |
|-----|--------------|-------|
| Watch | `/dashboard`, `/live-market` | Prices/charts only |
| Analyze (deep) | `/chart-analyzer` — **AI Market Analyzer** | Decision → Trade Levels → Chart → SMC → Vision (protected layout) |
| Discover | `/market-opportunities` | Multi-pair scanner → open Analyzer |
| Trade plan focused | `/trade-setups` | Entry/SL/TP/sizing + Decision (no Vision) |
| SMC technical | `/market-analysis` | Structure/Liquidity/OB-FVG/Indicators/MTF (no Vision) |
| Review | `/history` | Persisted Analyze runs (6.0.3.1) |
| Replay | `/backtesting` | Historical replay stack (separate from Analyzer) |
| Account | `/settings` | Local prefs until settings persistence |

Deferred nav (no dedicated product UX yet): `/trade-journal`, `/analytics` — performance today lives inside Replay.

## Phase table

| Phase | Status | User-facing surface | Canonical doc | Notes |
|-------|--------|---------------------|---------------|-------|
| 1 Scaffold | shipped | App shell | — | Health + dashboard |
| 2 Market data | shipped | Live Market, Overview | [architecture.md](architecture.md) | REST OHLCV + tickers |
| 2.5 WebSocket | shipped | Live charts / WS hub | [api.md](api.md) | `/ws/market` |
| 3.1 Indicators | shipped | Analyzer + SMC page | [indicators.md](indicators.md) | |
| 3.2 Structure | shipped | Analyzer + SMC page | [strategy_definitions.md](strategy_definitions.md) | |
| 3.3 Liquidity | shipped | Analyzer + SMC page | [liquidity_definitions.md](liquidity_definitions.md) | |
| 3.4 OB / FVG | shipped | Analyzer + SMC page | [ob_fvg_definitions.md](ob_fvg_definitions.md) | |
| ICT sessions / kill zones | not started | — | [strategy_definitions.md](strategy_definitions.md) | Empty `analysis/ict` reserved |
| 4.1 MTF | shipped | `/multi-timeframe`, Analyzer, SMC | [multi_timeframe_architecture.md](multi_timeframe_architecture.md) | Readiness orchestration |
| 4.2 Confluence | shipped | Analyzer | [confluence_engine.md](confluence_engine.md) | |
| 4.3 Trade plan | shipped | Analyzer + Trade Setups | [trade_plan_engine.md](trade_plan_engine.md) | Hypothetical levels only |
| 4.4 Decision | shipped | Analyzer + Trade Setups | [final_decision_engine.md](final_decision_engine.md) | LONG/SHORT/WAIT/NO TRADE |
| 5.1 Replay | shipped | `/backtesting` | [PHASE_5_1_HISTORICAL_REPLAY.md](PHASE_5_1_HISTORICAL_REPLAY.md) | Package: `backend/app/replay/` |
| 5.2.1–5.2.8 | shipped | Replay panels | `PHASE_5_2_*` | Analysis, sim, costs, analytics, robustness, reporting, seek, overlays |
| 5.3 / 5.3.1 | shipped | Analyzer chart overlays | `PHASE_5_3_*` | Trade-plan viz + monitor |
| 5.4.x Vision / Analyzer | shipped | AI Market Analyzer | `PHASE_5_4_*` | Upload + live Analyze |
| 5.5 Opportunities MVP | shipped | `/market-opportunities` | `PHASE_5_5_*` | In-memory store |
| 6.0.1 DB design | shipped (docs) | — | `PHASE_6_0_1_*` | |
| 6.0.2 Persistence foundation | shipped | — | [PHASE_6_0_2_PERSISTENCE_FOUNDATION.md](PHASE_6_0_2_PERSISTENCE_FOUNDATION.md) | Package: `backend/app/db/` |
| 6.0.3 Analyze soft-persist | shipped | Analyze + History | [PHASE_6_0_3_ANALYSIS_PERSISTENCE.md](PHASE_6_0_3_ANALYSIS_PERSISTENCE.md) | |
| 6.0.3.1 History UI | shipped | `/history` | [PHASE_6_0_3_1_ANALYSIS_HISTORY.md](PHASE_6_0_3_1_ANALYSIS_HISTORY.md) | |
| 6.0.4 Replay persistence | not started | — | migration plan | Do not merge Replay into Analyzer |
| 6.0.5–6.0.6 Journal / sim durability | not started | stubs only | — | `/trade-journal`, `/analytics` |
| 7 Docker / full QA | not started | — | — | |

## Backend layout notes

| Path | Role |
|------|------|
| `backend/app/db/` | Real persistence (SQLAlchemy / Alembic) |
| `backend/app/replay/` | Real historical replay / backtesting stack |
| `backend/app/database/` | Unused shell — ignore |
| `backend/app/backtesting/` | Unused shell — real code is `replay/` |
| `backend/app/analysis/ict/`, `analysis/smc/` | Reserved empty — engines live under structure/liquidity/ob_fvg |
