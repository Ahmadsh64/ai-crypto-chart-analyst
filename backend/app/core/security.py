"""Authentication helpers — Supabase Auth JWT validation (ES256 JWKS + legacy HS256)."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Annotated, Any

import httpx
import jwt
from fastapi import Depends, Header, HTTPException, WebSocket, status
from jwt import InvalidTokenError
from jwt.algorithms import ECAlgorithm

from app.core.config import Settings, get_settings

ALLOWED_ASYMMETRIC_ALGS = frozenset({"ES256"})
ALLOWED_LEGACY_ALGS = frozenset({"HS256"})
FORBIDDEN_ALGS = frozenset({"none", "None", "NONE"})

# Bounded JWKS cache (seconds). Unknown kid forces one refresh; failures are not sticky.
JWKS_CACHE_TTL_SECONDS = 600.0
JWKS_HTTP_TIMEOUT_SECONDS = 5.0
AUTH_USER_HTTP_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class AuthUser:
    """Authenticated caller derived from a verified Supabase access token."""

    sub: str
    email: str
    role: str | None = None


class AuthMisconfiguredError(RuntimeError):
    """Raised when AUTH_ENABLED is true but required configuration is missing."""


@dataclass
class _JwksCacheState:
    keys_by_kid: dict[str, Any] = field(default_factory=dict)
    fetched_at: float = 0.0
    jwks_url: str = ""


_jwks_cache = _JwksCacheState()
_jwks_lock = asyncio.Lock()


def _settings_ready_for_auth(settings: Settings) -> None:
    if not settings.auth_enabled:
        return
    if not settings.supabase_url.strip():
        raise AuthMisconfiguredError("AUTH_ENABLED requires SUPABASE_URL")
    if not settings.supabase_anon_key.strip():
        raise AuthMisconfiguredError("AUTH_ENABLED requires SUPABASE_ANON_KEY")
    if not settings.auth_allowed_email_list:
        raise AuthMisconfiguredError("AUTH_ENABLED requires AUTH_ALLOWED_EMAILS")


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _read_unverified_header(token: str) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except InvalidTokenError as exc:
        raise _unauthorized("Malformed access token") from exc
    if not isinstance(header, dict):
        raise _unauthorized("Malformed access token")
    return header


def _enforce_allowlist(email: str, sub: str, role: str | None, settings: Settings) -> AuthUser:
    email_n = email.strip().lower()
    sub_n = sub.strip()
    if not email_n or not sub_n:
        raise _unauthorized("Token missing required identity claims")

    allowed = {e.lower() for e in settings.auth_allowed_email_list}
    if email_n not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email is not authorized for this application",
        )
    return AuthUser(sub=sub_n, email=email_n, role=role)


def _parse_ec_jwk(jwk: dict[str, Any]) -> Any | None:
    """Return a cryptography public key for an ES256 / P-256 JWK, else None."""
    if str(jwk.get("kty") or "").upper() != "EC":
        return None
    crv = str(jwk.get("crv") or "")
    if crv not in {"P-256", "secp256r1"}:
        return None
    alg = jwk.get("alg")
    if alg is not None and str(alg) not in ALLOWED_ASYMMETRIC_ALGS:
        return None
    try:
        return ECAlgorithm.from_jwk(json.dumps(jwk))
    except Exception:  # noqa: BLE001 — ignore unusable JWKs
        return None


async def _fetch_jwks_keys(settings: Settings) -> dict[str, Any]:
    url = settings.supabase_jwks_url
    try:
        async with httpx.AsyncClient(timeout=JWKS_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication key service unavailable",
        ) from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication key service unavailable",
        )

    try:
        body = response.json()
        keys = body.get("keys") if isinstance(body, dict) else None
        if not isinstance(keys, list):
            raise ValueError("invalid JWKS")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication key service unavailable",
        ) from exc

    parsed: dict[str, Any] = {}
    for jwk in keys:
        if not isinstance(jwk, dict):
            continue
        kid = str(jwk.get("kid") or "").strip()
        if not kid:
            continue
        key = _parse_ec_jwk(jwk)
        if key is not None:
            parsed[kid] = key
    return parsed


async def _get_jwks_key(kid: str, settings: Settings, *, force_refresh: bool = False) -> Any:
    global _jwks_cache
    now = time.monotonic()
    async with _jwks_lock:
        cache_fresh = (
            not force_refresh
            and _jwks_cache.jwks_url == settings.supabase_jwks_url
            and (now - _jwks_cache.fetched_at) < JWKS_CACHE_TTL_SECONDS
            and bool(_jwks_cache.keys_by_kid)
        )
        if cache_fresh and kid in _jwks_cache.keys_by_kid:
            return _jwks_cache.keys_by_kid[kid]

        # Refresh when stale, forced, empty, URL changed, or kid unknown.
        keys = await _fetch_jwks_keys(settings)
        _jwks_cache = _JwksCacheState(
            keys_by_kid=keys,
            fetched_at=time.monotonic(),
            jwks_url=settings.supabase_jwks_url,
        )
        if kid not in _jwks_cache.keys_by_kid:
            raise _unauthorized("Unknown signing key")
        return _jwks_cache.keys_by_kid[kid]


def reset_jwks_cache() -> None:
    """Test helper — clear in-process JWKS cache."""
    global _jwks_cache
    _jwks_cache = _JwksCacheState()


async def _verify_es256(token: str, header: dict[str, Any], settings: Settings) -> AuthUser:
    kid = str(header.get("kid") or "").strip()
    if not kid:
        raise _unauthorized("Missing signing key id")

    # Fresh cache miss for kid forces one JWKS refresh inside _get_jwks_key.
    key = await _get_jwks_key(kid, settings, force_refresh=False)

    try:
        payload = jwt.decode(
            token,
            key=key,
            algorithms=["ES256"],
            audience="authenticated",
            issuer=settings.supabase_auth_issuer,
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
    except InvalidTokenError as exc:
        raise _unauthorized("Invalid or expired access token") from exc

    email = str(payload.get("email") or "")
    sub = str(payload.get("sub") or "")
    role = payload.get("role")
    return _enforce_allowlist(
        email,
        sub,
        str(role) if role is not None else None,
        settings,
    )


async def _verify_hs256_via_supabase_auth(token: str, settings: Settings) -> AuthUser:
    """
    Verify a legacy HS256 access token by asking Supabase Auth.

    Never trusts locally decoded JWT claims for HS256 — Auth server is the verifier.
    """
    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/user"
    headers = {
        "Authorization": f"Bearer {token}",
        "apikey": settings.supabase_anon_key.strip(),
    }
    try:
        async with httpx.AsyncClient(timeout=AUTH_USER_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(url, headers=headers)
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from exc

    if response.status_code in {401, 403}:
        raise _unauthorized("Invalid or expired access token")
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )

    try:
        body = response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from exc

    if not isinstance(body, dict):
        raise _unauthorized("Invalid or expired access token")

    email = str(body.get("email") or "")
    sub = str(body.get("id") or body.get("sub") or "")
    role = body.get("role")
    return _enforce_allowlist(
        email,
        sub,
        str(role) if role is not None else None,
        settings,
    )


async def verify_supabase_access_token(
    token: str,
    settings: Settings | None = None,
) -> AuthUser:
    """
    Validate a Supabase Auth access token and enforce the email allowlist.

    - ES256: verify locally with JWKS (kid selection, iss/aud/exp).
    - HS256: verify remotely via Supabase Auth ``/auth/v1/user`` (no local trust).
    Never logs the token.
    """
    cfg = settings or get_settings()
    _settings_ready_for_auth(cfg)

    if not token or not token.strip():
        raise _unauthorized("Missing access token")

    token = token.strip()
    header = _read_unverified_header(token)
    alg = str(header.get("alg") or "").strip()

    if not alg or alg in FORBIDDEN_ALGS:
        raise _unauthorized("Invalid token algorithm")
    if alg in ALLOWED_ASYMMETRIC_ALGS:
        return await _verify_es256(token, header, cfg)
    if alg in ALLOWED_LEGACY_ALGS:
        return await _verify_hs256_via_supabase_auth(token, cfg)
    raise _unauthorized("Unsupported token algorithm")


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
        raise _unauthorized("Authentication required")
    return await verify_supabase_access_token(token, settings)


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
        return await verify_supabase_access_token(token, settings)
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
