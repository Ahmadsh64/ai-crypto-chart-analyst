# Phase 6.0.1 — Database Schema

PostgreSQL 15+ recommended. Schema name: `public` (initial).

**Refinement 6.0.1.1:** deterministic event idempotency, `analysis_run_id`, financial reconstruction columns, composite ledger FKs, explicit `NUMERIC(p,s)` everywhere financial.

## 1. Financial precision policy (mandatory)

| Kind | PostgreSQL type | Notes |
|------|-----------------|-------|
| Prices (entry, SL, TP, marks, reference/execution) | `NUMERIC(28, 12)` | |
| Quantities / notionals | `NUMERIC(28, 12)` | Partial exits |
| Fees / slippage / spread / gross & net PnL | `NUMERIC(28, 12)` | Frozen at execution time |
| Fee rates | `NUMERIC(18, 10)` | Fraction e.g. `0.001` |
| RR / percentages | `NUMERIC(18, 8)` | |
| Confluence scores | `NUMERIC(10, 4)` | Non-monetary |

**Forbidden:** `DOUBLE PRECISION`, `REAL`, unspecified bare `NUMERIC` without precision for financial columns.

### JSONB serialization

- Financial values inside JSONB → **decimal strings**.
- Filter/sort/compare fields also have typed NUMERIC columns.
- Canonical hashing: sorted keys, UTF-8, decimal strings without scientific notation, UTC ISO timestamps (see architecture §8).

## 2. Common columns

- Prefer existing business string IDs as PKs where they exist (`rp_…`, `st_…`, `se_…`, `ec_…`, `decision_id`, `plan_id`, `report_id`).
- Otherwise `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`.
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`; mutable rows also `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`.
- All timestamps: timezone-aware UTC.

## 3. Entity definitions

### 3.1 `analysis_sessions`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| exchange | TEXT NOT NULL | |
| market_type | TEXT NOT NULL | |
| symbol | TEXT NOT NULL | |
| primary_timeframe | TEXT NULL | |
| status | TEXT NOT NULL | `active` / `closed` / `archived` |
| source | TEXT NOT NULL | `chart_analyzer` / `api` |
| created_at / updated_at | TIMESTAMPTZ NOT NULL | |

Index: `(exchange, market_type, symbol, created_at DESC)`.

### 3.2 `analysis_snapshots`

Append-only immutable historical record.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| analysis_session_id | UUID NULL FK → analysis_sessions **ON DELETE SET NULL** | |
| analysis_run_id | TEXT NOT NULL | Correlates Decision+Plan+Snapshot for one orchestration |
| snapshot_kind | TEXT NOT NULL | `live_ai_snapshot` / `live_decision_bundle` / `historical_replay` |
| exchange / market_type / symbol | TEXT NOT NULL | |
| timeframe | TEXT NULL | |
| analysis_timestamp | TIMESTAMPTZ NOT NULL | Prefer decision ts |
| decision_analysis_timestamp | TIMESTAMPTZ NULL | Provenance |
| trade_plan_analysis_timestamp | TIMESTAMPTZ NULL | Provenance |
| consistency_status | TEXT NOT NULL | `ALIGNED` / `DUAL_FETCH_DIVERGED` / `DECISION_ONLY` / `PLAN_ONLY` / `INSUFFICIENT_PROVENANCE` |
| decision | TEXT NOT NULL | |
| decision_id | TEXT NULL | Original business id |
| plan_id | TEXT NULL | Original business id |
| configuration_versions | JSONB NOT NULL | |
| snapshot_schema_version | TEXT NOT NULL | `analysis-snapshot-db-v1` |
| data_freshness | TEXT NULL | |
| entry_reference_price | NUMERIC(28,12) NULL | Decision-preferred extract |
| entry_low / entry_high | NUMERIC(28,12) NULL | |
| stop_loss_price | NUMERIC(28,12) NULL | |
| take_profit_prices | JSONB NOT NULL DEFAULT '[]' | decimal strings |
| primary_rr | NUMERIC(18,8) NULL | |
| confluence_bullish / confluence_bearish | NUMERIC(10,4) NULL | |
| snapshot_payload | JSONB NOT NULL | Both raw payloads + provenance; never merged prices |
| content_hash | TEXT NOT NULL | SHA-256 canonical payload |
| created_at | TIMESTAMPTZ NOT NULL | |

Constraints:

- `UNIQUE (analysis_run_id)` — one persisted snapshot row per run (re-save = idempotent same hash or conflict).
- `UNIQUE (snapshot_kind, content_hash)` — soft dedupe.
- Check: `consistency_status IN (...)`.

**Divergent runs:** payload keeps both originals; extracts remain decision-preferred; status = `DUAL_FETCH_DIVERGED`.

Example payload fragment:

```json
{
  "schema": "analysis-snapshot-db-v1",
  "analysis_run_id": "ar_…",
  "consistency_status": "DUAL_FETCH_DIVERGED",
  "decision_analysis_timestamp": "2026-11-14T13:28:10.103609Z",
  "trade_plan_analysis_timestamp": "2026-11-14T13:28:11.500000Z",
  "analysis_snapshot": { "decision": "NO TRADE", "entry_reference_price": null },
  "raw_decision": { "decision_id": "…", "stop_loss_price": null },
  "raw_trade_plan": { "plan_id": "…", "plan_status": "blocked" }
}
```

### 3.3 `decisions`

| Column | Type |
|--------|------|
| id | UUID PK |
| analysis_snapshot_id | UUID NOT NULL FK → analysis_snapshots **ON DELETE RESTRICT** |
| analysis_run_id | TEXT NOT NULL |
| decision_id | TEXT NULL |
| decision | TEXT NOT NULL |
| decision_reason | TEXT NOT NULL |
| lifecycle | TEXT NULL |
| direction | TEXT NULL |
| bullish_score / bearish_score | NUMERIC(10,4) NULL |
| evidence_payload | JSONB NOT NULL DEFAULT '[]' |
| conflicts_payload | JSONB NOT NULL DEFAULT '[]' |
| blocking_conditions | JSONB NOT NULL DEFAULT '[]' |
| configuration_version | TEXT NOT NULL |
| analysis_timestamp | TIMESTAMPTZ NOT NULL |
| created_at | TIMESTAMPTZ NOT NULL |

- `UNIQUE (decision_id)` WHERE decision_id IS NOT NULL
- `UNIQUE (analysis_run_id)` (one decision extract per run)
- Index: `(analysis_run_id)`, `(analysis_snapshot_id)`

### 3.4 `trade_plans`

| Column | Type |
|--------|------|
| id | UUID PK |
| analysis_snapshot_id | UUID NOT NULL FK → analysis_snapshots **ON DELETE RESTRICT** |
| analysis_run_id | TEXT NOT NULL |
| plan_id | TEXT NULL |
| direction | TEXT NULL |
| plan_status | TEXT NOT NULL |
| entry_reference_price / entry_low / entry_high | NUMERIC(28,12) NULL |
| stop_loss_price | NUMERIC(28,12) NULL |
| take_profit_targets | JSONB NOT NULL DEFAULT '[]' |
| primary_rr | NUMERIC(18,8) NULL |
| eligibility_payload | JSONB NOT NULL |
| plan_payload | JSONB NOT NULL |
| configuration_version | TEXT NOT NULL |
| analysis_timestamp | TIMESTAMPTZ NOT NULL |
| created_at | TIMESTAMPTZ NOT NULL |

- `UNIQUE (plan_id)` WHERE plan_id IS NOT NULL
- `UNIQUE (analysis_run_id)`
- Planned prices are **not** fills.

### 3.5 `replay_sessions`

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | Existing `session_id` `rp_…` |
| exchange / market_type / symbol | TEXT NOT NULL | |
| start_time / end_time | TIMESTAMPTZ NOT NULL | |
| timeframes | JSONB NOT NULL | |
| status / speed | TEXT NOT NULL | |
| event_index | INT NOT NULL DEFAULT 0 | |
| event_count | INT NOT NULL DEFAULT 0 | |
| replay_timestamp | TIMESTAMPTZ NULL | |
| config_version | TEXT NOT NULL | |
| configuration | JSONB NOT NULL | |
| data_quality | TEXT NULL | |
| limitations | JSONB NOT NULL DEFAULT '[]' | |
| error | TEXT NULL | |
| created_at / updated_at | TIMESTAMPTZ NOT NULL | |

### 3.6 `historical_analysis_snapshots`

| Column | Type |
|--------|------|
| id | UUID PK |
| replay_session_id | TEXT NOT NULL FK → replay_sessions **ON DELETE RESTRICT** |
| event_index | INT NOT NULL |
| replay_timestamp | TIMESTAMPTZ NOT NULL |
| decision / decision_reason / lifecycle_status | TEXT NOT NULL |
| decision_id / trade_plan_id | TEXT NULL |
| bullish_score / bearish_score | NUMERIC(10,4) NOT NULL |
| entry_reference_price / stop_loss_price | NUMERIC(28,12) NULL |
| take_profit_prices | JSONB NOT NULL DEFAULT '[]' |
| risk_reward | NUMERIC(18,8) NULL |
| snapshot_payload | JSONB NOT NULL |
| config_version | TEXT NOT NULL |
| analysis_versions | JSONB NOT NULL |
| content_hash | TEXT NOT NULL |
| created_at | TIMESTAMPTZ NOT NULL |

`UNIQUE (replay_session_id, event_index)`.

### 3.7 `simulated_trades`

Materialized **current** trade state.

| Column | Type |
|--------|------|
| trade_id | TEXT PK | Deterministic (architecture §6.2) |
| replay_session_id | TEXT NOT NULL FK → replay_sessions **ON DELETE RESTRICT** |
| signal_key | TEXT NOT NULL |
| signal_id | TEXT NULL |
| exchange / symbol / market_type | TEXT NOT NULL |
| direction | TEXT NOT NULL |
| decision | TEXT NOT NULL |
| decision_timestamp | TIMESTAMPTZ NOT NULL |
| decision_event_index | INT NOT NULL |
| lifecycle_status | TEXT NOT NULL |
| entry_zone | JSONB NULL | Planned zone — not a fill |
| entry_limit_price / entry_price | NUMERIC(28,12) NULL | `entry_price` = fill when opened |
| entry_timestamp / exit_timestamp | TIMESTAMPTZ NULL | |
| initial_stop_loss / current_stop_loss | NUMERIC(28,12) NOT NULL | Planned/current analytical SL |
| take_profit_levels / tp_allocations / tp_filled | JSONB NOT NULL | Levels ≠ fills |
| original_quantity | NUMERIC(28,12) NOT NULL | |
| remaining_quantity | NUMERIC(28,12) NOT NULL | |
| executed_quantity | NUMERIC(28,12) NOT NULL DEFAULT 0 | |
| quantity_closed_tp / quantity_closed_sl / quantity_closed_expired | NUMERIC(28,12) NOT NULL DEFAULT 0 | |
| expires_at | TIMESTAMPTZ NULL | |
| rejection_reason | TEXT NULL | |
| ambiguity_warnings | JSONB NOT NULL DEFAULT '[]' | |
| risk_reward | NUMERIC(18,8) NULL | |
| decision_reason | TEXT NULL | |
| decision_id / plan_id | TEXT NULL | |
| config_version | TEXT NOT NULL | |
| trade_payload | JSONB NOT NULL | Full dump; decimals as strings |
| created_at / updated_at | TIMESTAMPTZ NOT NULL | |

Constraints:

- `UNIQUE (trade_id, replay_session_id)` — supports composite FKs from children.
- Index `(replay_session_id, decision_event_index)`, `(lifecycle_status)`.

### 3.8 `trade_events`

Append-only history. **Idempotent** on deterministic `event_id`.

| Column | Type | Notes |
|--------|------|-------|
| event_id | TEXT PK | Deterministic global id (architecture §6.3) |
| trade_id | TEXT NOT NULL | |
| replay_session_id | TEXT NOT NULL | Must match parent trade |
| event_type | TEXT NOT NULL | SimulationEventType |
| event_timestamp | TIMESTAMPTZ NOT NULL | |
| price | NUMERIC(28,12) NULL | Fill price when applicable |
| quantity | NUMERIC(28,12) NULL | Fill qty when applicable |
| remaining_quantity | NUMERIC(28,12) NULL | |
| tp_index | INT NULL | |
| tp_index_key | INT NOT NULL | `COALESCE(tp_index, -1)` stored generated/persisted |
| candle_open_time | TIMESTAMPTZ NULL | |
| reason | TEXT NULL | |
| ambiguity_policy_applied | TEXT NULL | e.g. conservative_stop_first |
| metadata | JSONB NOT NULL DEFAULT '{}' | |
| payload_hash | TEXT NOT NULL | Canonical hash of mutable financial fields |
| event_payload | JSONB NOT NULL | Full original event |
| created_at | TIMESTAMPTZ NOT NULL | |

Constraints:

```text
PRIMARY KEY (event_id)
UNIQUE (trade_id, event_id)                          -- composite FK target for ledger
UNIQUE (replay_session_id, trade_id, event_type, candle_open_time, tp_index_key)
FOREIGN KEY (trade_id, replay_session_id)
  REFERENCES simulated_trades (trade_id, replay_session_id)
  ON DELETE RESTRICT
```

**Insert policy:** same `event_id` + same `payload_hash` → idempotent; same `event_id` + different hash → **conflict, no overwrite**.

Index: `(trade_id, event_timestamp)`.

### 3.9 `execution_cost_ledger`

Append-only; amounts frozen with model versions.

| Column | Type |
|--------|------|
| execution_id | TEXT PK | Stable idempotency key (`ec_{event_id}` or `ec_{event_id}_{role}`) |
| source_event_id | TEXT NOT NULL | Originating trade event |
| trade_id | TEXT NOT NULL | |
| replay_session_id | TEXT NOT NULL | |
| event_timestamp | TIMESTAMPTZ NOT NULL | |
| exchange / market_type / symbol | TEXT NOT NULL | |
| direction | TEXT NOT NULL | |
| execution_role | TEXT NOT NULL | `entry` / `exit` / … |
| order_type_estimate | TEXT NOT NULL | |
| maker_taker | TEXT NOT NULL | |
| maker_taker_estimated | BOOLEAN NOT NULL | |
| executed_quantity | NUMERIC(28,12) NOT NULL | |
| reference_price | NUMERIC(28,12) NOT NULL | |
| execution_price | NUMERIC(28,12) NOT NULL | |
| executed_notional | NUMERIC(28,12) NOT NULL | |
| fee_rate | NUMERIC(18,10) NOT NULL | |
| fee_amount | NUMERIC(28,12) NOT NULL | |
| slippage_amount | NUMERIC(28,12) NOT NULL | |
| spread_cost | NUMERIC(28,12) NOT NULL | |
| gross_realized_pnl | NUMERIC(28,12) NULL | |
| allocated_entry_fee | NUMERIC(28,12) NULL | |
| net_realized_pnl | NUMERIC(28,12) NULL | |
| cost_model_version | TEXT NOT NULL | |
| fee_schedule_version | TEXT NOT NULL | |
| fee_config_source | TEXT NOT NULL | |
| assumptions / warnings | JSONB NOT NULL DEFAULT '[]' | |
| metadata | JSONB NOT NULL DEFAULT '{}' | |
| created_at | TIMESTAMPTZ NOT NULL | |

Constraints:

```text
PRIMARY KEY (execution_id)
UNIQUE (trade_id, source_event_id, execution_role)
FOREIGN KEY (trade_id, source_event_id)
  REFERENCES trade_events (trade_id, event_id)
  ON DELETE RESTRICT
FOREIGN KEY (trade_id, replay_session_id)
  REFERENCES simulated_trades (trade_id, replay_session_id)
  ON DELETE RESTRICT
```

Effects:

- Ledger cannot point at an event for another trade.
- Multiple cost rows per event only when `execution_role` differs.
- Session must match the trade’s session.

### 3.10 `backtest_reports`

| Column | Type |
|--------|------|
| report_id | TEXT PK |
| replay_session_id | TEXT NOT NULL FK → replay_sessions **ON DELETE RESTRICT** |
| report_schema_version | TEXT NOT NULL |
| generated_at | TIMESTAMPTZ NOT NULL |
| replay_timestamp | TIMESTAMPTZ NULL |
| event_index | INT NULL |
| exchange / symbol / market_type | TEXT NOT NULL |
| analytics_version / cost_model_version | TEXT NULL |
| report_payload | JSONB NOT NULL | Decimals as strings |
| created_at | TIMESTAMPTZ NOT NULL |

### 3.11 `trade_journal_entries`

| Column | Type |
|--------|------|
| id | UUID PK |
| simulated_trade_id | TEXT NOT NULL FK → simulated_trades **ON DELETE RESTRICT** |
| title | TEXT NOT NULL |
| notes | TEXT NOT NULL DEFAULT '' |
| setup_type | TEXT NULL |
| tags | JSONB NOT NULL DEFAULT '[]' |
| lessons_learned | TEXT NULL |
| created_at / updated_at | TIMESTAMPTZ NOT NULL |

Journal DELETE/UPDATE never cascades into trades, events, ledger, or reports.

## 4. Delete behavior

| Parent | Child | ON DELETE |
|--------|-------|-----------|
| analysis_sessions | analysis_snapshots | SET NULL |
| analysis_snapshots | decisions / trade_plans | **RESTRICT** |
| replay_sessions | historical snapshots / trades / reports | **RESTRICT** |
| simulated_trades | trade_events / ledger / journal | **RESTRICT** |
| trade_events | ledger (via composite FK) | **RESTRICT** |

No `ON DELETE CASCADE` on financial history.

## 5. Reconstruction cheat-sheet

1. Order `trade_events` by `(event_timestamp, event_id)`.
2. Apply quantity rules (architecture §7).
3. Join ledger on `(trade_id, source_event_id)`.
4. Sum exit `net_realized_pnl` / fees; compare to materialization — **audit only** by default.

## 6. Indexes (performance)

1. `analysis_snapshots (analysis_run_id)` UNIQUE
2. `analysis_snapshots (exchange, market_type, symbol, analysis_timestamp DESC)`
3. `analysis_snapshots (consistency_status, analysis_timestamp DESC)`
4. `simulated_trades (replay_session_id, lifecycle_status)`
5. `trade_events (trade_id, event_timestamp)`
6. `execution_cost_ledger (replay_session_id, event_timestamp)`
7. Defer GIN on JSONB until proven needed.

## 7. Retention

Unchanged: soft-archive sessions; keep financial history unless explicitly purged with RESTRICT-aware tooling. No partitioning in 6.0.x by default.
