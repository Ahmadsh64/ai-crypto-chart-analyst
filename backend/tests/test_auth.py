"""Personal-beta authentication tests (Supabase JWT gate)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings
from app.main import app

JWT_SECRET = "test-supabase-jwt-secret-for-unit-tests-only"
ALLOWED_EMAIL = "owner@example.com"
OTHER_EMAIL = "intruder@example.com"


def _clear_settings() -> None:
    get_settings.cache_clear()


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("AUTH_ALLOWED_EMAILS", ALLOWED_EMAIL)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DOCS_ENABLED", "false")
    _clear_settings()
    yield
    _clear_settings()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _make_token(
    email: str = ALLOWED_EMAIL,
    *,
    secret: str = JWT_SECRET,
    aud: str = "authenticated",
    exp_offset: int = 3600,
    sub: str = "user-sub-1",
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


def test_health_remains_public_when_auth_enabled(auth_env: None, client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_unauthenticated_rest_rejected(auth_env: None, client: TestClient) -> None:
    response = client.get("/api/v1/opportunities/status")
    assert response.status_code == 401


def test_authenticated_rest_succeeds(auth_env: None, client: TestClient) -> None:
    token = _make_token()
    response = client.get(
        "/api/v1/opportunities/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


def test_unauthorized_email_rejected(auth_env: None, client: TestClient) -> None:
    token = _make_token(OTHER_EMAIL)
    response = client.get(
        "/api/v1/opportunities/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_scanner_unauthenticated_rejected(auth_env: None, client: TestClient) -> None:
    response = client.post("/api/v1/opportunities/scan")
    assert response.status_code == 401


def test_scanner_authenticated_accepted(
    auth_env: None, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auth must pass before scan logic runs (scan itself is stubbed)."""
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

    monkeypatch.setattr(opportunities_routes, "get_scanner", lambda: _StubScanner())
    token = _make_token()
    response = client.post(
        "/api/v1/opportunities/scan",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


def test_docs_disabled_in_production_flag(auth_env: None, client: TestClient) -> None:
    # Docs URLs are bound at create_app(); when DOCS_ENABLED=false via env at
    # process start they are off. Re-create app for this assertion.
    from app.main import create_app

    _clear_settings()
    fresh = create_app()
    fresh_client = TestClient(fresh)
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


def test_unauthenticated_websocket_rejected(auth_env: None, client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws/market"):
            pass
    assert excinfo.value.code == 4401


def test_authenticated_websocket_connects(auth_env: None, client: TestClient) -> None:
    token = _make_token()
    with client.websocket_connect(f"/ws/market?access_token={token}") as ws:
        msg = ws.receive_json()
        assert msg.get("type") == "connection_status"
        assert msg.get("status") == "connected"


def test_auth_disabled_allows_anonymous(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "false")
    _clear_settings()
    response = client.get("/api/v1/opportunities/status")
    assert response.status_code == 200
