"""Phase 6.0.2 — secure Supabase TLS CA configuration tests."""

from __future__ import annotations

import ssl
from pathlib import Path

import pytest

from app.core.config import Settings
from app.db.ssl_config import (
    SslConfigurationError,
    backend_root,
    build_supabase_ssl_context,
    is_supabase_database_url,
    resolve_ssl_ca_file_path,
    sanitize_tls_error_text,
    ssl_connect_arg_for_url,
)


@pytest.fixture
def loadable_ca_file() -> Path:
    project_ca = backend_root() / "prod-ca-2021.crt"
    if project_ca.is_file():
        return project_ca
    pytest.skip("backend/prod-ca-2021.crt required for loadable CA unit tests")


def test_is_supabase_url_detection():
    assert is_supabase_database_url(
        "postgresql+asyncpg://u:p@aws-0-x.pooler.supabase.com:5432/postgres"
    )
    assert is_supabase_database_url(
        "postgresql+asyncpg://u:p@db.ref.supabase.co:5432/postgres"
    )
    assert not is_supabase_database_url(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_crypto_chart"
    )


def test_resolve_relative_ca_against_backend_root(tmp_path: Path, monkeypatch):
    # Create file under real backend root name via absolute configured path
    ca = tmp_path / "custom-ca.crt"
    ca.write_bytes(b"-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n")
    resolved = resolve_ssl_ca_file_path(str(ca), allow_project_default=False)
    assert resolved == ca.resolve()
    assert resolved.is_absolute()


def test_supabase_url_selects_custom_ca_ssl_context(loadable_ca_file: Path):
    settings = Settings(
        persistence_enabled=True,
        supabase_ssl_ca_file=str(loadable_ca_file),
        supabase_db_url="postgresql+asyncpg://u:p@aws-0-x.pooler.supabase.com:5432/postgres",
    )
    url = settings.effective_database_url
    ctx = ssl_connect_arg_for_url(url, settings)
    assert isinstance(ctx, ssl.SSLContext)


def test_ssl_context_cert_required_and_hostname(loadable_ca_file: Path):
    ctx = build_supabase_ssl_context(loadable_ca_file)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_missing_configured_ca_file_fails_safely(tmp_path: Path):
    missing = tmp_path / "does-not-exist.crt"
    settings = Settings(
        persistence_enabled=True,
        supabase_ssl_ca_file=str(missing),
        supabase_db_url="postgresql+asyncpg://u:p@aws-0-x.pooler.supabase.com:5432/postgres",
    )
    with pytest.raises(SslConfigurationError) as ei:
        ssl_connect_arg_for_url(settings.effective_database_url, settings)
    msg = str(ei.value)
    assert "missing" in msg.lower()
    assert "postgresql" not in msg.lower()
    assert "://" not in msg


def test_invalid_ca_file_fails_safely(tmp_path: Path):
    bad = tmp_path / "bad.crt"
    bad.write_text("not-a-certificate\n", encoding="utf-8")
    settings = Settings(
        persistence_enabled=True,
        supabase_ssl_ca_file=str(bad),
        supabase_db_url="postgresql+asyncpg://u:p@aws-0-x.pooler.supabase.com:5432/postgres",
    )
    with pytest.raises(SslConfigurationError) as ei:
        ssl_connect_arg_for_url(settings.effective_database_url, settings)
    msg = str(ei.value)
    assert "valid pem" in msg.lower() or "invalid" in msg.lower()
    assert "://" not in msg


def test_non_supabase_database_unchanged():
    settings = Settings(
        persistence_enabled=True,
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/ai_crypto_chart",
        supabase_db_url="",
        supabase_ssl_ca_file="/should/not/be/used.crt",
    )
    url = settings.effective_database_url
    assert "localhost" in url
    assert ssl_connect_arg_for_url(url, settings) is None


def test_sanitize_strips_urls_and_userinfo():
    raw = (
        "error postgresql+asyncpg://user:secret@aws-0-x.pooler.supabase.com:5432/postgres boom"
    )
    cleaned = sanitize_tls_error_text(raw)
    assert "secret" not in cleaned
    assert "postgresql+asyncpg://" not in cleaned
    assert "<redacted_url>" in cleaned
    assert "supabase.com" not in cleaned.lower() or "<redacted_host>" in cleaned


@pytest.mark.asyncio
async def test_get_engine_supabase_uses_ssl_context(loadable_ca_file: Path, monkeypatch):
    from app.db import session as session_mod

    monkeypatch.setattr(session_mod, "_engine", None)
    monkeypatch.setattr(session_mod, "_session_factory", None)
    settings = Settings(
        persistence_enabled=True,
        supabase_ssl_ca_file=str(loadable_ca_file),
        supabase_db_url="postgresql+asyncpg://u:p@aws-0-x.pooler.supabase.com:5432/postgres",
        db_pool_size=1,
        db_max_overflow=0,
    )
    engine = session_mod.get_engine(settings)
    assert engine is not None
    ctx = ssl_connect_arg_for_url(settings.effective_database_url, settings)
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
    await engine.dispose()
    monkeypatch.setattr(session_mod, "_engine", None)
    monkeypatch.setattr(session_mod, "_session_factory", None)
