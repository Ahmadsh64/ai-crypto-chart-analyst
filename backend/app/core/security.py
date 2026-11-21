"""Authentication helpers — Supabase Auth JWT validation for personal beta."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, WebSocket, status
from jwt import InvalidTokenError

from app.core.config import Settings, get_settings


@dataclass(frozen=True, slots=True)
class AuthUser:
    """Authenticated caller derived from a Supabase access token."""

    sub: str
    email: str
    role: str | None = None


class AuthMisconfiguredError(RuntimeError):
    """Raised when AUTH_ENABLED is true but required secrets are missing."""


def _settings_ready_for_auth(settings: Settings) -> None:
    if not settings.auth_enabled:
        return
    if not settings.supabase_jwt_secret.strip():
        raise AuthMisconfiguredError("AUTH_ENABLED requires SUPABASE_JWT_SECRET")
    if not settings.auth_allowed_email_list:
        raise AuthMisconfiguredError("AUTH_ENABLED requires AUTH_ALLOWED_EMAILS")


def verify_supabase_access_token(
    token: str,
    settings: Settings | None = None,
) -> AuthUser:
    """
    Validate a Supabase Auth access token (HS256) and enforce the email allowlist.

    Never logs the token. Rejects expired / wrong-audience / non-allowlisted emails.
    """
    cfg = settings or get_settings()
    _settings_ready_for_auth(cfg)

    if not token or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            token.strip(),
            cfg.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={"require": ["exp", "sub", "aud"]},
        )
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    email = str(payload.get("email") or "").strip().lower()
    sub = str(payload.get("sub") or "").strip()
    if not email or not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing required claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    allowed = {e.lower() for e in cfg.auth_allowed_email_list}
    if email not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email is not authorized for this application",
        )

    role = payload.get("role")
    return AuthUser(sub=sub, email=email, role=str(role) if role else None)


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


async def require_authenticated_user(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthUser | None:
    """
    FastAPI dependency for protected REST routes.

    When AUTH_ENABLED is false (local/tests default), returns None and allows the request.
    When AUTH_ENABLED is true, requires a valid Supabase Bearer access token.
    """
    settings = get_settings()
    if not settings.auth_enabled:
        return None

    try:
        _settings_ready_for_auth(settings)
    except AuthMisconfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is misconfigured",
        ) from exc

    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_supabase_access_token(token, settings)


# Router-level dependency list used by create_app for all application APIs.
require_auth_dependencies = [Depends(require_authenticated_user)]


async def authenticate_websocket(websocket: WebSocket) -> AuthUser | None:
    """
    Authenticate a WebSocket before the application accepts the connection.

    Token sources (in order):
    1. ``access_token`` query parameter
    2. ``Authorization: Bearer …`` header (when the client can send it)

    When AUTH_ENABLED is false, returns None without closing the socket.
    On failure, closes with code 4401 and returns None (caller must not accept).
    """
    settings = get_settings()
    if not settings.auth_enabled:
        return None

    try:
        _settings_ready_for_auth(settings)
    except AuthMisconfiguredError:
        await websocket.close(code=1011, reason="Auth misconfigured")
        return None

    token = websocket.query_params.get("access_token")
    if not token:
        auth_header = websocket.headers.get("authorization")
        token = _extract_bearer(auth_header)

    if not token:
        await websocket.close(code=4401, reason="Authentication required")
        return None

    try:
        return verify_supabase_access_token(token, settings)
    except HTTPException:
        await websocket.close(code=4401, reason="Invalid or unauthorized token")
        return None


# ---------------------------------------------------------------------------
# Legacy optional API-key helper (unused by current routes; kept for reference)
# ---------------------------------------------------------------------------


async def verify_optional_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str | None:
    """Optional API-key gate. Prefer Supabase JWT auth for production."""
    settings = get_settings()
    expected = getattr(settings, "app_api_key", None)
    if not expected:
        return x_api_key
    if x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key
