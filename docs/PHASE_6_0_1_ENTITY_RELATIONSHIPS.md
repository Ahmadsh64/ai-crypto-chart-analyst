# Phase 6.0.1 — Entity Relationships

**Refinement 6.0.1.1:** `analysis_run_id` correlation; composite FKs for events/ledger; RESTRICT-only financial deletes.

## 1. Conceptual model

- **Live path:** `analysis_sessions` 1—* `analysis_snapshots` ; each snapshot shares `analysis_run_id` with 0..1 `decisions` and 0..1 `trade_plans`
- **Replay path:** `replay_sessions` 1—* `historical_analysis_snapshots`, `simulated_trades`, `backtest_reports`
- **Simulation path:** `simulated_trades` 1—* `trade_events` 1—* `execution_cost_ledger` ; `simulated_trades` 1—* `trade_journal_entries`

No `users` entity.

## 2. Integrity edges (critical)

```
simulated_trades (trade_id, replay_session_id)
    ↑ FK
trade_events (trade_id, replay_session_id)
    ↑ FK (trade_id, source_event_id) → (trade_id, event_id)
execution_cost_ledger
```

- Event session must equal trade session.
- Ledger event must belong to same trade (composite FK).
- Journal cannot delete or mutate financial parents (RESTRICT + app rules).

## 3. Mermaid ER diagram

```mermaid
erDiagram
    ANALYSIS_SESSIONS ||--o{ ANALYSIS_SNAPSHOTS : groups
    ANALYSIS_SNAPSHOTS ||--o| DECISIONS : run
    ANALYSIS_SNAPSHOTS ||--o| TRADE_PLANS : run

    REPLAY_SESSIONS ||--o{ HISTORICAL_ANALYSIS_SNAPSHOTS : produces
    REPLAY_SESSIONS ||--o{ SIMULATED_TRADES : simulates
    REPLAY_SESSIONS ||--o{ BACKTEST_REPORTS : reports

    SIMULATED_TRADES ||--o{ TRADE_EVENTS : emits
    TRADE_EVENTS ||--o{ EXECUTION_COST_LEDGER : costs
    SIMULATED_TRADES ||--o{ EXECUTION_COST_LEDGER : owns
    SIMULATED_TRADES ||--o{ TRADE_JOURNAL_ENTRIES : journals

    ANALYSIS_SESSIONS {
        uuid id PK
        text exchange
        text market_type
        text symbol
        text status
    }

    ANALYSIS_SNAPSHOTS {
        uuid id PK
        uuid analysis_session_id FK
        text analysis_run_id UK
        text consistency_status
        timestamptz decision_analysis_timestamp
        timestamptz trade_plan_analysis_timestamp
        jsonb snapshot_payload
        text content_hash
    }

    DECISIONS {
        uuid id PK
        uuid analysis_snapshot_id FK
        text analysis_run_id UK
        text decision_id UK
        text decision
    }

    TRADE_PLANS {
        uuid id PK
        uuid analysis_snapshot_id FK
        text analysis_run_id UK
        text plan_id UK
        text plan_status
        numeric entry_reference_price
    }

    REPLAY_SESSIONS {
        text id PK
        text exchange
        text symbol
        text market_type
        int event_index
        text status
    }

    HISTORICAL_ANALYSIS_SNAPSHOTS {
        uuid id PK
        text replay_session_id FK
        int event_index
        text decision
        jsonb snapshot_payload
    }

    SIMULATED_TRADES {
        text trade_id PK
        text replay_session_id FK
        text lifecycle_status
        numeric remaining_quantity
        numeric executed_quantity
        jsonb trade_payload
    }

    TRADE_EVENTS {
        text event_id PK
        text trade_id FK
        text replay_session_id FK
        text event_type
        numeric price
        numeric quantity
        text payload_hash
    }

    EXECUTION_COST_LEDGER {
        text execution_id PK
        text source_event_id FK
        text trade_id FK
        text execution_role
        numeric fee_amount
        numeric net_realized_pnl
        text cost_model_version
    }

    BACKTEST_REPORTS {
        text report_id PK
        text replay_session_id FK
        timestamptz generated_at
        jsonb report_payload
    }

    TRADE_JOURNAL_ENTRIES {
        uuid id PK
        text simulated_trade_id FK
        text title
        text notes
    }
```

## 4. Cardinality notes

| Relationship | Cardinality | Notes |
|--------------|-------------|-------|
| Snapshot ↔ Decision extract | 1:0..1 | Same `analysis_run_id` |
| Snapshot ↔ Trade plan extract | 1:0..1 | Same `analysis_run_id` |
| Trade → Events | 1:N | Append-only; idempotent `event_id` |
| Event → Ledger | 1:N | At most one row per `(event, execution_role)` |
| Trade → Journal | 1:N | Metadata only |

## 5. Diagram location

Canonical ER for Phase 6.0.1 / 6.0.1.1: this file.
