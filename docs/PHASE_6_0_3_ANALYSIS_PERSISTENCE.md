# Phase 6.0.3 — Automatic Analysis Persistence

**Status:** Implemented  
**Scope:** Soft-fail persistence of live Analyze bundles to Supabase.  
**Out of scope:** History APIs/UI (later), replay/sim persistence (6.0.4+), formula changes.

## Behavior

1. User triggers Analyze (`POST /api/v1/ai/analyze` or `/analyze-with-vision`).
2. Existing deterministic Decision + Trade Plan + snapshot run unchanged.
3. One `analysis_run_id` (`ar_…`) is allocated for the orchestration.
4. Soft persist via `persist_live_analyze_bundle`:
   - get/create `analysis_sessions` (active)
   - atomic TX: snapshot + decision + trade_plan extracts
5. Analyze response always returns analysis results; plus:
   - `analysis_run_id`
   - `persistence_status`: `disabled` | `saved` | `idempotent` | `failed` | `conflict`
   - optional safe `persistence_detail` / `consistency_status` / `persisted_snapshot_id`

Vision remains observational and does not alter Entry/SL/TP/decision.  
`/analyze-with-vision` persists **at most one** bundle per request.

## Failure policy

DB errors never fail Analyze. Server logs use a correlation id (`analysis_run_id`) and sanitized messages (no URLs/passwords).

## Integration points

| Layer | Location |
|-------|----------|
| Soft persist service | `app/services/analysis_persistence_service.py` |
| Atomic repo | `app/db/repositories/analysis.py` |
| Routes | `app/api/routes/ai.py` |
| Response schema | `app/api/schemas/ai.py` |
| Frontend status line | Chart Analyzer Analyze panel |

Replay routes do **not** call live persistence.
