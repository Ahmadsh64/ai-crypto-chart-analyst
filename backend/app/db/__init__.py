"""Phase 6.0.2 — optional Supabase PostgreSQL persistence foundation."""

from app.db.identity import (
    compute_payload_hash,
    deterministic_event_id,
    deterministic_execution_id,
    deterministic_trade_id,
    new_analysis_run_id,
    new_replay_session_id,
    stable_replay_session_id,
)
from app.db.session import (
    close_db,
    get_async_session_factory,
    get_engine,
    init_db,
    is_persistence_active,
    session_scope,
)

__all__ = [
    "close_db",
    "compute_payload_hash",
    "deterministic_event_id",
    "deterministic_execution_id",
    "deterministic_trade_id",
    "get_async_session_factory",
    "get_engine",
    "init_db",
    "is_persistence_active",
    "new_analysis_run_id",
    "new_replay_session_id",
    "session_scope",
    "stable_replay_session_id",
]
