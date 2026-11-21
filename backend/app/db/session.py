"""Async SQLAlchemy engine / session management (Phase 6.0.2)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.ssl_config import (
    SslConfigurationError,
    sanitize_tls_error_text,
    ssl_connect_arg_for_url,
)

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def is_persistence_active(settings: Settings | None = None) -> bool:
    """True only when optional persistence is explicitly enabled."""
    cfg = settings or get_settings()
    return bool(cfg.persistence_enabled)


def get_engine(settings: Settings | None = None) -> AsyncEngine | None:
    """Return the process-wide async engine, or None if persistence is off."""
    global _engine, _session_factory
    cfg = settings or get_settings()
    if not cfg.persistence_enabled:
        return None
    if _engine is None:
        url = cfg.effective_database_url
        connect_args: dict[str, Any] = {
            "timeout": cfg.db_connect_timeout_seconds,
        }
        # Supabase: explicit verifying SSLContext (never ssl=True / CERT_NONE).
        # Non-Supabase URLs: leave SSL unchanged (typically local/dev without TLS).
        ssl_arg = ssl_connect_arg_for_url(url, cfg)
        if ssl_arg is not None:
            connect_args["ssl"] = ssl_arg
            logger.info(
                "Async SQLAlchemy engine using verifying Supabase SSL context "
                "(CERT_REQUIRED, check_hostname=True)"
            )
        _engine = create_async_engine(
            url,
            echo=cfg.database_echo,
            pool_size=cfg.db_pool_size,
            max_overflow=cfg.db_max_overflow,
            pool_timeout=cfg.db_pool_timeout_seconds,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        _session_factory = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        logger.info("Async SQLAlchemy engine created (persistence enabled)")
    return _engine


def get_async_session_factory(
    settings: Settings | None = None,
) -> async_sessionmaker[AsyncSession] | None:
    get_engine(settings)
    return _session_factory


async def init_db(settings: Settings | None = None) -> bool:
    """
    Initialize engine when persistence is enabled.
    Returns False when disabled — caller must not treat as failure.
    """
    cfg = settings or get_settings()
    if not cfg.persistence_enabled:
        logger.info("Persistence disabled — skipping DB init")
        return False
    try:
        engine = get_engine(cfg)
    except SslConfigurationError as exc:
        logger.warning("Database SSL configuration error: %s", exc)
        return False
    if engine is None:
        return False
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        logger.info("Database connectivity check succeeded")
        return True
    except Exception as exc:  # noqa: BLE001 — app must continue without DB
        logger.warning(
            "Database unavailable at startup: %s",
            sanitize_tls_error_text(str(exc)),
        )
        return False


async def close_db() -> None:
    """Dispose engine on shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        logger.info("Database engine disposed")
    _engine = None
    _session_factory = None


@asynccontextmanager
async def session_scope(
    settings: Settings | None = None,
) -> AsyncIterator[AsyncSession]:
    """
    Yield an AsyncSession when persistence is enabled.
    Raises PersistenceDisabledError when disabled.
    """
    from app.db.exceptions import PersistenceDisabledError

    factory = get_async_session_factory(settings)
    if factory is None:
        raise PersistenceDisabledError("Persistence is disabled")
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def ping_database(settings: Settings | None = None) -> tuple[str, str]:
    """
    Health probe. Returns (status, detail) where status is ok|degraded|unavailable.
    Never raises. Detail text is sanitized (no URLs/secrets).
    """
    cfg = settings or get_settings()
    if not cfg.persistence_enabled:
        return "ok", "Persistence disabled (optional)"
    try:
        engine = get_engine(cfg)
        if engine is None:
            return "unavailable", "Engine not initialized"
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return "ok", "Supabase/PostgreSQL reachable"
    except SslConfigurationError as exc:
        return "unavailable", sanitize_tls_error_text(str(exc))
    except Exception as exc:  # noqa: BLE001
        return "unavailable", sanitize_tls_error_text(f"Database unreachable: {exc}")
