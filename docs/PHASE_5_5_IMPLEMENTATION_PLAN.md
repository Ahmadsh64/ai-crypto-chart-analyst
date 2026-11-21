# Phase 5.5 — Market Opportunity Scanner — Implementation Plan

**Status:** Audit complete → implement in controlled steps  
**Protected:** AI Market Analyzer UI/UX (`docs/AI_MARKET_ANALYZER_UI_UX_SPEC.md`) — do not redesign

---

## 1. Architecture audit (summary)

### Reuse (do not duplicate)

| Capability | Location |
|------------|----------|
| Exchange adapters | `backend/app/exchanges/{binance,bybit,manager}.py` |
| Market discovery + TTL cache | `list_markets` + `MarketsMetadataCache` |
| OHLCV | `ExchangeManager.fetch_ohlcv` |
| Shared analysis context | `build_analysis_context` / `build_analysis_context_from_candles` |
| Engines | Structure, Liquidity, OB/FVG, MTF, Confluence, Trade Plan, Decision |
| Decision+plan path | Same as `compute_decision_response` (single context fetch) |

### Gaps to build

- Batch scanner orchestration + overlap lock  
- Per-exchange concurrency / rate-limit throttling  
- OHLCV TTL cache (none today except markets metadata)  
- Opportunity store + lifecycle/ranking  
- `/api/v1/opportunities*` APIs  
- Dedicated **Market Opportunities** frontend (not Analyzer, not Replay)  

### Persistence decision

- **Phase 5.5 MVP:** process-local in-memory opportunity + scan history store.  
- **No new Alembic migration** in this phase (avoids destructive/silent schema change).  
- **Proposed future schema** (document only): `scanner_runs`, `market_opportunities` with content-hash dedupe, lifecycle history, `source=market_scanner` — optional later under Phase 6.x.

### Notifications

- No external notification provider in repo.  
- Phase 5.5: in-API opportunity status only; optional notifications **documented, not integrated**.

---

## 2. Risks

| Risk | Mitigation |
|------|------------|
| Rate limits (4 TF × N symbols) | Bounded concurrency (default 2/exchange), OHLCV cache, max universe size, scan interval |
| Full universe scan cost | Liquidity/volume filter + `max_pairs_per_market` (default 25) |
| Dual-fetch debt | Scanner calls `build_analysis_context` **once** then plan + decision |
| Provider outage | Isolate per exchange; continue other provider |
| Analyzer / Replay breakage | Separate page + APIs; no engine formula changes; no Vision in scan |
| Multi-worker memory | Document process-local store limitation |

---

## 3. Scanner design

```
MarketsMetadataCache → filter active USDT + volume/liquidity → candidate list
  → overlap lock
  → per-exchange semaphore
  → OHLCV cache (MTF ladder)
  → build_analysis_context(_from_candles)
  → analyze_trade_plan → analyze_decision
  → map OpportunityStatus (READY / APPROACHING_ENTRY / WAITING / INVALIDATED / EXPIRED / DATA_UNAVAILABLE)
  → rank → OpportunityStore
```

**Eligibility (existing engines only):** actionable cards require Decision LONG/SHORT + valid trade plan + existing quality gates. WAIT/NO TRADE never become READY.

**Ranking:** READY first → confluence score desc → freshness → liquidity → entry distance. Explainable; not profitability.

**Vision:** never used in scanner.

---

## 4. API (planned)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/opportunities` | List/filter/sort |
| GET | `/api/v1/opportunities/{id}` | Detail |
| GET | `/api/v1/opportunities/status` | Scanner status + summary |
| GET | `/api/v1/opportunities/history` | Recent scan runs |
| POST | `/api/v1/opportunities/scan` | Manual refresh (non-overlapping) |

---

## 5. Frontend

- New nav: **Market Opportunities** → `/market-opportunities`  
- Summary metrics, filters, cards, Open Full Analysis → `/chart-analyzer?...` (query hydrate only; no Analyzer redesign)  
- Preserve dark/light tokens and responsive layout  

---

## 6. Controlled implementation steps

1. Plan + config + models + OHLCV cache  
2. Universe filter + analyze-one + store + scheduler  
3. FastAPI routes + tests  
4. Frontend dashboard + nav + Open Full Analysis  
5. Integration tests, build, browser QA, `docs/qa-artifacts/phase-5-5/QA_REPORT.md`  

**Out of scope:** Phase 6.0.4, engine formula changes, trading keys, order execution.
