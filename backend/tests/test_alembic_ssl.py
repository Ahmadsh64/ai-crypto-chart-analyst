"""Phase 6.0.2.1 — Alembic shares app TLS policy (no migrations executed)."""

from __future__ import annotations

import ssl
from pathlib import Path

import pytest

from app.core.config import Settings
from app.db.ssl_config import (
    SslConfigurationError,
    alembic_async_connect_args,
    alembic_database_url,
    backend_root,
    sanitize_tls_error_text,
)


@pytest.fixture
def loadable_ca_file() -> Path:
    path = backend_root() / "prod-ca-2021.crt"
    if not path.is_file():
        pytest.skip("backend/prod-ca-2021.crt required")
    return path


def test_alembic_url_matches_application_settings(loadable_ca_file: Path):
    settings = Settings(
        persistence_enabled=True,
        supabase_ssl_ca_file=str(loadable_ca_file),
        supabase_db_url=(
            "postgresql+asyncpg://u:p@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
        ),
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/local",
    )
    assert alembic_database_url(settings) == settings.effective_database_url
    assert "pooler.supabase.com" in alembic_database_url(settings)
    assert "localhost" not in alembic_database_url(settings).split("@")[-1]


def test_alembic_loads_ca_with_cert_required_and_hostname(loadable_ca_file: Path):
    settings = Settings(
        persistence_enabled=True,
        supabase_ssl_ca_file=str(loadable_ca_file),
        supabase_db_url=(
            "postgresql+asyncpg://u:p@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
        ),
    )
    args = alembic_async_connect_args(settings)
    assert "ssl" in args
    ctx = args["ssl"]
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_alembic_missing_ca_fails_safely(tmp_path: Path):
    missing = tmp_path / "missing-ca.crt"
    settings = Settings(
        persistence_enabled=True,
        supabase_ssl_ca_file=str(missing),
        supabase_db_url=(
            "postgresql+asyncpg://u:p@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
        ),
    )
    with pytest.raises(SslConfigurationError) as ei:
        alembic_async_connect_args(settings)
    msg = str(ei.value)
    assert "missing" in msg.lower()
    assert "://" not in msg
    assert "postgresql" not in msg.lower()


def test_alembic_invalid_ca_fails_safely(tmp_path: Path):
    bad = tmp_path / "bad.crt"
    bad.write_text("not-a-pem\n", encoding="utf-8")
    settings = Settings(
        persistence_enabled=True,
        supabase_ssl_ca_file=str(bad),
        supabase_db_url=(
            "postgresql+asyncpg://u:p@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
        ),
    )
    with pytest.raises(SslConfigurationError) as ei:
        alembic_async_connect_args(settings)
    assert "://" not in str(ei.value)


def test_alembic_non_supabase_unchanged():
    settings = Settings(
        persistence_enabled=True,
        supabase_db_url="",
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/ai_crypto_chart",
        supabase_ssl_ca_file="/unused/ca.crt",
    )
    assert alembic_database_url(settings) == settings.effective_database_url
    args = alembic_async_connect_args(settings)
    assert "ssl" not in args
    assert "timeout" in args


def test_sanitize_keeps_secrets_out_of_messages():
    dirty = "fail postgresql+asyncpg://user:secret@host/db detail"
    clean = sanitize_tls_error_text(dirty)
    assert "secret" not in clean
    assert "postgresql+asyncpg://" not in clean


def test_env_py_wires_ssl_helpers():
    """Static check: alembic/env.py reuses ssl_config helpers (no migration run)."""
    env_path = backend_root() / "alembic" / "env.py"
    text = env_path.read_text(encoding="utf-8")
    assert "alembic_async_connect_args" in text
    assert "alembic_database_url" in text
    assert "async_engine_from_config" in text
    assert "connect_args=connect_args" in text or "connect_args =" in text
    assert "CERT_NONE" not in text
    assert 'ssl=True' not in text
