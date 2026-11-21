"""Personal-beta authentication tests — ES256 JWKS + legacy HS256 remote verify."""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Iterator
from typing import Any
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core import security as security_mod
from app.core.config import get_settings
from app.core.security import _JwksCacheState
from app.main import app

SUPABASE_URL = "https://example.supabase.co"
ANON_KEY = "test-anon-key-not-a-secret"
ALLOWED_EMAIL = "owner@example.com"
OTHER_EMAIL = "intruder@example.com"
ISSUER = f"{SUPABASE_URL}/auth/v1"
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
KID = "test-es256-kid"


def _clear_settings() -> None:
    get_settings.cache_clear()
    security_mod.reset_jwks_cache()


@pytest.fixture
def ec_keypair() -> tuple[ec.EllipticCurvePrivateKey, Any]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    return private_key, private_key.public_key()


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_ANON_KEY", ANON_KEY)
    monkeypatch.setenv("AUTH_ALLOWED_EMAILS", ALLOWED_EMAIL)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DOCS_ENABLED", "false")
    _clear_settings()
    yield
    _clear_settings()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _seed_jwks_cache(public_key: Any, *, kid: str = KID) -> None:
    security_mod._jwks_cache = _JwksCacheState(
        keys_by_kid={kid: public_key},
        fetched_at=time.monotonic(),
        jwks_url=JWKS_URL,
    )


def _make_es256_token(
    private_key: ec.EllipticCurvePrivateKey,
    *,
    email: str = ALLOWED_EMAIL,
    aud: str = "authenticated",
    iss: str = ISSUER,
    exp_offset: int = 3600,
    sub: str = "user-sub-1",
    kid: str = KID,
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": sub,
        "email": email,
        "role": "authenticated",
        "aud": aud,
        "iss": iss,
        "iat": now,
        "exp": now + exp_offset,
    }
    return jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": kid})


def _make_hs256_token(
    email: str = ALLOWED_EMAIL,
    *,
    secret: str = "legacy-shared-secret-for-tests-only",
    aud: str = "authenticated",
    exp_offset: int = 3600,
    sub: str = "user-sub-hs256",
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": sub,
        "email": email,
        "role": "authenticated",
        "aud": aud,
        "iat": now,
        "exp": now + exp_offset,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


class _FakeAsyncClient:
    """Minimal AsyncClient stand-in for auth HTTP calls under TestClient."""

    def __init__(self, handler, *args: Any, **kwargs: Any) -> None:
        self._handler = handler

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def get(self, url: str, headers: dict[str, str] | None = None) -> httpx.Response:
        return await self._handler(url, headers or {})


def _patch_httpx(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    monkeypatch.setattr(
        security_mod.httpx,
        "AsyncClient",
        lambda *a, **k: _FakeAsyncClient(handler, *a, **k),
    )


# --- Health / regression surface ---


def test_health_remains_public_when_auth_enabled(auth_env: None, client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_unauthenticated_rest_rejected(auth_env: None, client: TestClient) -> None:
    response = client.get("/api/v1/opportunities/status")
    assert response.status_code == 401


def test_auth_disabled_allows_anonymous(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "false")
    _clear_settings()
    response = client.get("/api/v1/opportunities/status")
    assert response.status_code == 200


def test_docs_disabled_in_production_flag(auth_env: None, client: TestClient) -> None:
    from app.main import create_app

    _clear_settings()
    fresh_client = TestClient(create_app())
    assert fresh_client.get("/docs").status_code == 404
    assert fresh_client.get("/openapi.json").status_code == 404
    assert fresh_client.get("/redoc").status_code == 404


def test_cors_preflight_allows_configured_origin(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.main import create_app

    monkeypatch.setenv("CORS_ORIGINS", "https://example.vercel.app")
    _clear_settings()
    fresh_client = TestClient(create_app())
    response = fresh_client.options(
        "/api/v1/exchanges",
        headers={
            "Origin": "https://example.vercel.app",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code in {200, 204}
    assert response.headers.get("access-control-allow-origin") == "https://example.vercel.app"


# --- ES256 ---


def test_valid_es256_token_rest(
    auth_env: None,
    client: TestClient,
    ec_keypair: tuple[ec.EllipticCurvePrivateKey, Any],
) -> None:
    private_key, public_key = ec_keypair
    _seed_jwks_cache(public_key)
    token = _make_es256_token(private_key)
    response = client.get(
        "/api/v1/opportunities/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


def test_invalid_es256_signature_rejected(
    auth_env: None,
    client: TestClient,
    ec_keypair: tuple[ec.EllipticCurvePrivateKey, Any],
) -> None:
    _private_key, public_key = ec_keypair
    other_key = ec.generate_private_key(ec.SECP256R1())
    _seed_jwks_cache(public_key)
    token = _make_es256_token(other_key, kid=KID)
    response = client.get(
        "/api/v1/opportunities/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_unknown_kid_rejected(
    auth_env: None,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    ec_keypair: tuple[ec.EllipticCurvePrivateKey, Any],
) -> None:
    private_key, public_key = ec_keypair
    _seed_jwks_cache(public_key)

    async def _fetch(_settings: Any) -> dict[str, Any]:
        return {KID: public_key}

    monkeypatch.setattr(security_mod, "_fetch_jwks_keys", _fetch)
    token = _make_es256_token(private_key, kid="unknown-kid")
    response = client.get(
        "/api/v1/opportunities/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_expired_es256_rejected(
    auth_env: None,
    client: TestClient,
    ec_keypair: tuple[ec.EllipticCurvePrivateKey, Any],
) -> None:
    private_key, public_key = ec_keypair
    _seed_jwks_cache(public_key)
    token = _make_es256_token(private_key, exp_offset=-10)
    response = client.get(
        "/api/v1/opportunities/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_wrong_issuer_rejected(
    auth_env: None,
    client: TestClient,
    ec_keypair: tuple[ec.EllipticCurvePrivateKey, Any],
) -> None:
    private_key, public_key = ec_keypair
    _seed_jwks_cache(public_key)
    token = _make_es256_token(private_key, iss="https://other.supabase.co/auth/v1")
    response = client.get(
        "/api/v1/opportunities/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_wrong_audience_rejected(
    auth_env: None,
    client: TestClient,
    ec_keypair: tuple[ec.EllipticCurvePrivateKey, Any],
) -> None:
    private_key, public_key = ec_keypair
    _seed_jwks_cache(public_key)
    token = _make_es256_token(private_key, aud="anon")
    response = client.get(
        "/api/v1/opportunities/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_unauthorized_email_rejected_es256(
    auth_env: None,
    client: TestClient,
    ec_keypair: tuple[ec.EllipticCurvePrivateKey, Any],
) -> None:
    private_key, public_key = ec_keypair
    _seed_jwks_cache(public_key)
    token = _make_es256_token(private_key, email=OTHER_EMAIL)
    response = client.get(
        "/api/v1/opportunities/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_alg_none_rejected(auth_env: None, client: TestClient) -> None:
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        .rstrip(b"=")
        .decode()
    )
    payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {
                    "sub": "x",
                    "email": ALLOWED_EMAIL,
                    "aud": "authenticated",
                    "iss": ISSUER,
                    "exp": int(time.time()) + 3600,
                }
            ).encode()
        )
        .rstrip(b"=")
        .decode()
    )
    token = f"{header}.{payload}."
    response = client.get(
        "/api/v1/opportunities/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


# --- Legacy HS256 via Supabase Auth ---


def test_valid_legacy_hs256_via_supabase_auth(
    auth_env: None, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _make_hs256_token()
    seen: dict[str, Any] = {}

    async def handler(url: str, headers: dict[str, str]) -> httpx.Response:
        seen["url"] = url
        seen["authorization"] = headers.get("Authorization")
        seen["apikey"] = headers.get("apikey")
        return httpx.Response(
            200,
            json={"id": "user-sub-hs256", "email": ALLOWED_EMAIL, "role": "authenticated"},
            request=httpx.Request("GET", url),
        )

    _patch_httpx(monkeypatch, handler)
    response = client.get(
        "/api/v1/opportunities/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert seen["url"].endswith("/auth/v1/user")
    assert seen["authorization"] == f"Bearer {token}"
    assert seen["apikey"] == ANON_KEY


def test_invalid_legacy_hs256_rejected(
    auth_env: None, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _make_hs256_token()

    async def handler(url: str, headers: dict[str, str]) -> httpx.Response:
        return httpx.Response(
            401,
            json={"message": "invalid"},
            request=httpx.Request("GET", url),
        )

    _patch_httpx(monkeypatch, handler)
    response = client.get(
        "/api/v1/opportunities/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_legacy_hs256_supabase_timeout_fail_closed(
    auth_env: None, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _make_hs256_token()

    async def handler(url: str, headers: dict[str, str]) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    _patch_httpx(monkeypatch, handler)
    response = client.get(
        "/api/v1/opportunities/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503


def test_legacy_hs256_unauthorized_email(
    auth_env: None, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _make_hs256_token(OTHER_EMAIL)

    async def handler(url: str, headers: dict[str, str]) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": "intruder-id", "email": OTHER_EMAIL},
            request=httpx.Request("GET", url),
        )

    _patch_httpx(monkeypatch, handler)
    response = client.get(
        "/api/v1/opportunities/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


# --- Scanner / WebSocket ---


def test_scanner_unauthenticated_rejected(auth_env: None, client: TestClient) -> None:
    response = client.post("/api/v1/opportunities/scan")
    assert response.status_code == 401


def test_scanner_authenticated_accepted(
    auth_env: None,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    ec_keypair: tuple[ec.EllipticCurvePrivateKey, Any],
) -> None:
    from datetime import datetime, timezone

    from app.api.routes import opportunities as opportunities_routes
    from app.scanner.models import ScanRunSummary

    class _StubScanner:
        async def run_scan(self, *, trigger: str = "manual") -> ScanRunSummary:
            now = datetime.now(timezone.utc)
            return ScanRunSummary(
                scan_id="scan_test",
                started_at=now,
                finished_at=now,
                status="completed",
                opportunities_found=0,
                errors=[],
            )

    private_key, public_key = ec_keypair
    _seed_jwks_cache(public_key)
    monkeypatch.setattr(opportunities_routes, "get_scanner", lambda: _StubScanner())
    token = _make_es256_token(private_key)
    response = client.post(
        "/api/v1/opportunities/scan",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


def test_unauthenticated_websocket_rejected(auth_env: None, client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws/market"):
            pass
    assert excinfo.value.code == 4401


def test_authenticated_websocket_connects_before_accept(
    auth_env: None,
    client: TestClient,
    ec_keypair: tuple[ec.EllipticCurvePrivateKey, Any],
) -> None:
    private_key, public_key = ec_keypair
    _seed_jwks_cache(public_key)
    token = _make_es256_token(private_key)
    with client.websocket_connect(f"/ws/market?access_token={token}") as ws:
        msg = ws.receive_json()
        assert msg.get("type") == "connection_status"
        assert msg.get("status") == "connected"


def test_websocket_invalid_token_rejected_before_accept(
    auth_env: None,
    client: TestClient,
    ec_keypair: tuple[ec.EllipticCurvePrivateKey, Any],
) -> None:
    _private_key, public_key = ec_keypair
    _seed_jwks_cache(public_key)
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws/market?access_token=not-a-jwt"):
            pass
    assert excinfo.value.code == 4401
