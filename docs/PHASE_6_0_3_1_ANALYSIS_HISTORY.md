# Phase 6.0.3.1 — Analysis History REST API & UI

Read-only History surface over Phase 6.0.3 persisted Analyze bundles.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/history/analyses` | Paginated list + filters |
| GET | `/api/v1/history/analyses/by-run/{analysis_run_id}` | Preferred detail lookup |
| GET | `/api/v1/history/analyses/{analysis_run_id}` | Same as by-run; UUID snapshot id fallback |

### List query params

`limit` (1–200, default 50), `offset`, `exchange`, `market_type`, `symbol`, `timeframe`, `decision`, `consistency_status`, `from`, `to`.

Ordering: `analysis_timestamp DESC`, then `id DESC`.

### Availability

- Persistence disabled → **503** `PERSISTENCE_DISABLED` (never an empty list pretending “no history”).
- DB / session factory unavailable → **503** `DATABASE_UNAVAILABLE`.
- Missing run → **404** `ANALYSIS_NOT_FOUND`.

## Immutability

History routes only read `analysis_sessions` / `analysis_snapshots` / `decisions` / `trade_plans`. They do not call market providers, recompute indicators/SMC/confluence/Decision/Trade Plan, or rewrite levels.

## Frontend

- Nav item **History** → `/history`
- Filters: symbol, decision; pagination; row → detail drawer
- Planned Entry/SL/TP labeled as analytical (not fills)

## Out of scope

Replay persistence, simulation, journal, reports, auth, migrations, Phase 6.0.4.
