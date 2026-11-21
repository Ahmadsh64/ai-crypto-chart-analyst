# Phase 5.5 — Updated Spec Audit & Implementation Plan

**Status:** Steps 1–4 complete; Step 5 (API) not started — production migrate of 0004 not applied  
**Date:** 2026-11-20  
**Approved:** Option A (TF matrix), persistence tables (pending schema review in Step 3), max 25 pairs/market (Step 2 done)  
**Protected:** AI Market Analyzer UI/UX — no redesign  
**Out of scope:** Phase 6.0.4, engine formula changes, trading execution, Vision in scan

---

## 1. Architecture audit (current state)

### What already exists (Phase 5.5 MVP)

| Area | Status |
|------|--------|
| Binance + Bybit Spot + Futures market types in config | Present |
| Dynamic `list_markets` + USDT + volume filter | Present, but capped |
| 5-minute scheduler (`scan_interval_seconds=300`) | Present |
| Overlap lock, per-exchange semaphore, OHLCV TTL cache | Present |
| Reuse `build_analysis_context_from_candles` + Trade Plan + Decision | Present |
| Lifecycle statuses READY…DATA_UNAVAILABLE | Present |
| APIs: list / detail / status / history / scan | Present |
| Frontend `/market-opportunities` + Open Full Analysis | Present |
| In-memory store (no DB migration) | Present |
| MTF ladder fetch 4H→1H→15M→5M | Present |

### Persistence (Supabase / SQLAlchemy)

Existing tables (do not break):

- `analysis_sessions` (`source` defaults to `chart_analyzer`; has `primary_timeframe`)
- `analysis_snapshots` (immutable)
- `decisions`, `trade_plans` (Phase 6.0.2 / 6.0.3)

**No** `scanner_runs` / `market_opportunities` tables today. Scanner is process-local RAM.

### Engines (must not modify formulas)

- Decision / Trade Plan: `setup_timeframe=M15`, `confirmation_timeframe=M5` (locked configs)
- Confluence / MTF / Structure / Liquidity / OB-FVG: unchanged
- Scanner currently labels opportunities with `display_timeframe=H1` only
- Opportunity identity: `hash(exchange:market:symbol)` — **no timeframe dimension**

---

## 2. Gap analysis vs updated specification

| Requirement | Current | Gap |
|-------------|---------|-----|
| Spot **and** Futures (do not silently exclude) | Config includes both; scan runs both | **OK** — keep; add scan-summary breakdown by market type |
| Timeframes **5m, 15m, 1H, 4H** as selected analysis TFs | One analysis / pair; UI has **no** TF filter; label forced to H1 | **Major** — need multi-TF publication strategy (see §3) |
| MTF ladder preserved | Fetches full ladder | **OK** — must keep for every execution TF |
| Dynamic universe, no hardcoded list | Prefers `DEFAULT_SYMBOLS` majors; `max_pairs_per_market=6` | **Major** — raise cap; volume-rank primary; majors only as soft tie-break |
| Refresh every 5 minutes | 300s default | **OK** |
| Scanner enabled when configured | `enabled=True`, `auto_start=True` | **OK** — expose config health in status |
| Summary: waiting / invalidated / next refresh | Partial (ready/long/short/next_scan_at) | **Minor** — add waiting + invalidated/expired counts to status API + UI |
| Filters include timeframe | Missing | **Required** |
| Persist identity across refresh; optional history | In-memory upsert by id | **Product decision** — schema proposal in §5; implement only after approval |
| Acceptance: setups across Spot+Futures × 4 TFs | Not met | **Must close** before PASS |

---

## 3. Proposed scanner architecture

### 3.1 Data flow

```
list_markets (Binance, Bybit) × {spot, futures}
  → active USDT + volume/liquidity filter (dynamic, capped for rate limits)
  → candidate set
  → for each candidate × each execution_tf in {5m, 15m, 1H, 4H}:
        load MTF OHLCV (4H→1H→15M→5M) via TTL cache (shared across TF runs)
        build_analysis_context_from_candles (closed candles only)
        analyze_trade_plan + analyze_decision  [existing engines only]
        classify lifecycle status
  → stable opportunity_id = hash(exchange|market|symbol|execution_tf)
  → rank → publish store
```

### 3.2 Multi-timeframe product interpretation (OPEN DECISION — needs approval)

**Problem:** Engines today compute one Decision/Trade Plan per MTF context with fixed setup=M15 / confirm=M5. Publishing four independent “setups” per pair requires a defined meaning.

**Recommended Option A — Execution-TF matrix (matches acceptance wording)**

- For each `execution_tf` ∈ {5m, 15m, 1H, 4H}, call existing engines with a **non-formula** config overlay:
  - Map setup/confirmation roles onto the ladder so HTF context is never omitted
  - Example mapping (illustrative; finalize in implementation step 1):
    - execution 5m → setup M15, confirm M5 (native)
    - execution 15m → setup M15, confirm M5 (native)
    - execution 1H → setup H1, confirm M15 (still loads 4H context)
    - execution 4H → setup H4, confirm H1
- **Do not** change confluence weights, RR formulas, or eligibility thresholds
- Only use existing engine parameters; document mapping in QA report

**Option B — Single native analysis, TF as filter metadata**

- One Decision/Trade Plan per pair (native M15/M5)
- Dashboard TF filter filters by which ladder TFs were ready / by display tag
- **Fails** strict acceptance (“across 5m, 15m, 1H, and 4H” as distinct setups)

**Default proposal for review: Option A.**  
If rejected, Option B cannot claim full acceptance without product waiver.

### 3.3 Rate-limit / performance strategy

| Control | Proposed default |
|---------|------------------|
| Interval | 300s exact |
| Concurrency / exchange | 2 |
| OHLCV TTL | 90–120s (shared across TF matrix) |
| Max pairs / market type / exchange | Raise from 6 → **25** (configurable; volume-ranked) |
| TF matrix | 4 execution TFs; candle fetch deduped by cache |
| Overlap | Skip if prior scan still running |
| Priority | Previously READY/APPROACHING first within fair round-robin of universe |
| Vision | Never in scanner |

**Risk:** 2 exchanges × ~2 market types × 25 pairs × 4 TF analyses ≈ up to ~400 analyze calls/cycle; OHLCV largely cached after first TF. First cold scan may exceed 5 minutes → overlap lock + status `scanning` until done; next cycle waits.

### 3.4 Eligibility / lifecycle (unchanged rules)

- READY only when existing Decision is LONG/SHORT **and** Trade Plan valid under existing gates  
- WAIT → WAITING; NO TRADE → not actionable (EXPIRED / INVALIDATED / non-actionable as mapped today)  
- Never invent Entry/SL/TP; show Unavailable  
- Planned levels ≠ fills  

### 3.5 Ranking (explainable, no new eligibility)

1. Actionable (READY) first  
2. Existing confluence score ↓  
3. Freshness  
4. Liquidity  
5. Distance to entry zone  
6. MTF readiness / alignment flags from existing context  

Copy: ranking ≠ profitability.

---

## 4. API contract (extend existing — no duplicates)

Keep `/api/v1/opportunities*`.

| Change | Detail |
|--------|--------|
| `GET /opportunities` | Add `timeframe` filter; return TF on each card |
| `GET /opportunities/status` | Add `waiting_count`, `invalidated_or_expired_count`, market-type/TF coverage flags, `config` snapshot |
| `POST /opportunities/scan` | Unchanged (non-overlapping) |
| `GET /opportunities/history` | Unchanged (scan runs); optional later: lifecycle history if DB approved |

---

## 5. Persistence impact assessment

### Recommendation for this revision

| Approach | Pros | Cons |
|----------|------|------|
| **A. Keep in-memory + stable IDs** (default if DB deferred) | No migration risk; identity across cycles in one process | Lost on restart; not multi-worker |
| **B. Minimal new tables** | Survives restart; history | Needs migration approval |

### Proposed schema (document only until approved) — Option B

```text
scanner_runs
  id, started_at, finished_at, status, pairs_targeted, pairs_scanned,
  pairs_failed, ready_count, errors jsonb, trigger

market_opportunities
  opportunity_id (pk, stable hash incl. timeframe)
  exchange, market_type, symbol, timeframe
  status, decision, confluence_score, levels jsonb
  analysis_timestamp, content_hash, updated_at
  UNIQUE(exchange, market_type, symbol, timeframe)

market_opportunity_events  (optional lifecycle history)
  id, opportunity_id, from_status, to_status, at, payload jsonb
```

**Rules:**

- `source` for any linked analysis session would be `market_scanner` — never rewrite chart_analyzer rows  
- No destructive changes to 6.0.3 tables  
- Upsert by `opportunity_id`; unchanged `content_hash` → update timestamp only  

**This plan defaults to Option A (in-memory) unless you approve Option B migrations.**

---

## 6. Frontend plan (Market Opportunities only)

- Add **Timeframe** filter: 5m / 15m / 1H / 4H / All  
- Summary: scanned, qualified/READY, LONG, SHORT, waiting, invalidated|expired, last scan, **next refresh**  
- Keep READY vs non-actionable visual separation  
- Open Full Analysis → Analyzer with exchange, market, pair, **timeframe** query params  
- Do **not** touch Analyzer layout / workflows  

---

## 7. Controlled implementation steps (after approval)

1. Confirm Option A vs B (TF matrix) and persistence A vs B  
2. Config: raise universe cap; volume-first discovery; `execution_timeframes` list; remove hard major-only gate  
3. Analyze path: stable id includes TF; engine config overlay for execution TF; shared OHLCV cache  
4. Status API + summary fields; ranking unchanged formulas  
5. Frontend filters/summary/TF display  
6. Expand tests (Spot/Futures × exchanges × 4 TFs, overlap, WAIT exclusion, etc.)  
7. Live scan metrics + browser QA + update `docs/qa-artifacts/phase-5-5/QA_REPORT.md`  

**Stop condition:** Phase 5.5 complete; **do not** start Phase 6.0.4.

---

## 8. Decisions required from you before coding

1. **Multi-TF strategy:** Option A (execution-TF matrix with setup/confirm role mapping) vs Option B (single native analysis)?  
2. **Persistence:** Keep in-memory (A) vs approve minimal `scanner_runs` / `market_opportunities` migration (B)?  
3. **Universe size:** Confirm `max_pairs_per_market=25` (or name another cap) for rate-limit safety?  

No implementation will start until these are approved.
