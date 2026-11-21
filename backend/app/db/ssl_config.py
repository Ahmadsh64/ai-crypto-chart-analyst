"""Secure TLS helpers for Supabase PostgreSQL (Phase 6.0.2).

Uses an explicit SSLContext with CERT_REQUIRED and hostname verification.
Never disables certificate verification.
"""

from __future__ import annotations

import re
import ssl
from pathlib import Path

from app.core.config import Settings

# backend/app/db/ssl_config.py → backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CA_NAME = "prod-ca-2021.crt"


class SslConfigurationError(Exception):
    """Raised when a required TLS CA file is missing or invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(sanitize_tls_error_text(message))


def backend_root() -> Path:
    """Deterministic backend package root (independent of process cwd)."""
    return _BACKEND_ROOT


def default_supabase_ca_path() -> Path:
    return backend_root() / _DEFAULT_CA_NAME


def is_supabase_database_url(url: str) -> bool:
    low = (url or "").lower()
    return "supabase.com" in low or "supabase.co" in low


def sanitize_tls_error_text(text: str) -> str:
    """Strip connection URLs / userinfo from error text before logging."""
    out = text or ""
    out = re.sub(r"[a-zA-Z]+[+a-zA-Z]*://\S+", "<redacted_url>", out)
    out = re.sub(
        r"(://)([^:/@]+):([^@/]+)@",
        r"\1<redacted_user>:<redacted_pass>@",
        out,
    )
    out = re.sub(
        r"\b[a-z0-9][a-z0-9\-.]+\.(supabase\.(?:co|com))\b",
        "<redacted_host>",
        out,
        flags=re.I,
    )
    return out


def resolve_ssl_ca_file_path(
    configured: str | None,
    *,
    allow_project_default: bool = True,
) -> Path | None:
    """
    Resolve SUPABASE_SSL_CA_FILE.

    - Absolute paths used as-is.
    - Relative paths resolved against the backend root (not cwd).
    - Empty configured value → optional default ``backend/prod-ca-2021.crt``
      when that file exists and ``allow_project_default`` is True.
    """
    raw = (configured or "").strip()
    if raw:
        path = Path(raw)
        if not path.is_absolute():
            path = backend_root() / path
        return path.resolve()
    if allow_project_default:
        default = default_supabase_ca_path()
        if default.is_file():
            return default.resolve()
    return None


def build_supabase_ssl_context(ca_path: Path) -> ssl.SSLContext:
    """
    Build a verifying SSL context for asyncpg.

    Preserves CERT_REQUIRED and check_hostname=True.
    Raises SslConfigurationError if the CA file is missing or not a usable PEM.
    """
    if not ca_path.is_file():
        raise SslConfigurationError(
            f"Configured Supabase SSL CA file is missing: {ca_path.name}"
        )
    try:
        data = ca_path.read_bytes()
    except OSError as exc:
        raise SslConfigurationError(
            f"Unable to read Supabase SSL CA file: {ca_path.name} ({exc})"
        ) from exc
    if b"BEGIN CERTIFICATE" not in data:
        raise SslConfigurationError(
            f"Supabase SSL CA file is not a valid PEM certificate: {ca_path.name}"
        )
    try:
        ctx = ssl.create_default_context(cafile=str(ca_path))
    except ssl.SSLError as exc:
        raise SslConfigurationError(
            f"Supabase SSL CA file is invalid: {ca_path.name} "
            f"({sanitize_tls_error_text(str(exc))})"
        ) from exc
    except OSError as exc:
        raise SslConfigurationError(
            f"Supabase SSL CA file could not be loaded: {ca_path.name}"
        ) from exc

    # Explicitly assert secure defaults (create_default_context already sets these).
    if ctx.verify_mode != ssl.CERT_REQUIRED:
        raise SslConfigurationError("SSL context verify_mode must remain CERT_REQUIRED")
    if not ctx.check_hostname:
        raise SslConfigurationError("SSL context check_hostname must remain enabled")
    return ctx


def ssl_connect_arg_for_url(url: str, settings: Settings) -> ssl.SSLContext | None:
    """
    Return SSLContext for Supabase URLs, or None for non-Supabase targets.

    Never returns a weakened context. Never falls back to ssl=True / CERT_NONE.
    """
    if not is_supabase_database_url(url):
        return None

    configured = (settings.supabase_ssl_ca_file or "").strip()
    ca_path = resolve_ssl_ca_file_path(
        configured,
        allow_project_default=True,
    )
    if ca_path is None:
        raise SslConfigurationError(
            "Supabase TLS requires SUPABASE_SSL_CA_FILE or "
            f"the project default {_DEFAULT_CA_NAME} under the backend root"
        )
    # If explicitly configured, missing file must fail (resolve already absolute).
    if configured and not ca_path.is_file():
        raise SslConfigurationError(
            f"Configured Supabase SSL CA file is missing: {ca_path.name}"
        )
    return build_supabase_ssl_context(ca_path)


def alembic_database_url(settings: Settings | None = None) -> str:
    """Same effective DB URL the app and Alembic must share."""
    from app.core.config import get_settings

    cfg = settings or get_settings()
    return cfg.effective_database_url


def alembic_async_connect_args(settings: Settings | None = None) -> dict:
    """
    connect_args for Alembic's async SQLAlchemy engine (asyncpg).

    Mirrors ``app.db.session.get_engine`` TLS policy:
    - Supabase → verifying SSLContext (CERT_REQUIRED, check_hostname=True)
    - Non-Supabase → no ssl key (unchanged local/dev behavior)
    """
    from app.core.config import get_settings

    cfg = settings or get_settings()
    url = cfg.effective_database_url
    connect_args: dict = {
        "timeout": cfg.db_connect_timeout_seconds,
    }
    ssl_ctx = ssl_connect_arg_for_url(url, cfg)
    if ssl_ctx is not None:
        connect_args["ssl"] = ssl_ctx
    return connect_args
