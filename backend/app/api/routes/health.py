"""Health-check endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter

from app import __version__
from app.api.schemas.health import ComponentStatus, HealthResponse
from app.core.config import get_settings
from app.db.session import ping_database
from app.exchanges.manager import get_exchange_manager

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return service health including optional live exchange reachability."""
    settings = get_settings()

    exchange_status: str = "unavailable"
    exchange_detail = "Exchange adapters unavailable"
    try:
        pings = await get_exchange_manager().ping_all()
        online = [ex.value for ex, ok in pings.items() if ok]
        offline = [ex.value for ex, ok in pings.items() if not ok]
        if online and not offline:
            exchange_status = "ok"
            exchange_detail = f"Reachable: {', '.join(online)}"
        elif online:
            exchange_status = "degraded"
            exchange_detail = f"Reachable: {', '.join(online)}; offline: {', '.join(offline)}"
        else:
            exchange_status = "unavailable"
            exchange_detail = "Binance and Bybit unreachable"
    except Exception as exc:  # noqa: BLE001 - health must never crash
        exchange_status = "unavailable"
        exchange_detail = f"Exchange check failed: {exc}"

    db_status, db_detail = await ping_database(settings)

    components = [
        ComponentStatus(name="api", status="ok", detail="FastAPI process running"),
        ComponentStatus(
            name="database",
            status=db_status,  # type: ignore[arg-type]
            detail=db_detail,
        ),
        ComponentStatus(name="exchanges", status=exchange_status, detail=exchange_detail),  # type: ignore[arg-type]
        ComponentStatus(
            name="openai",
            status="ok" if settings.openai_api_key else "unavailable",
            detail="Configured" if settings.openai_api_key else "OPENAI_API_KEY not set",
        ),
    ]

    # Persistence is optional: DB unavailable must not take the API down.
    overall: str = "ok"
    if any(c.status == "unavailable" for c in components if c.name == "api"):
        overall = "unavailable"
    else:
        non_db_degraded = any(
            c.status == "degraded" for c in components if c.name != "database"
        )
        db_degraded = settings.persistence_enabled and any(
            c.name == "database" and c.status != "ok" for c in components
        )
        if non_db_degraded or db_degraded:
            overall = "degraded"

    return HealthResponse(
        status=overall,  # type: ignore[arg-type]
        service=settings.app_name,
        version=__version__,
        environment=settings.environment,
        timestamp=datetime.now(timezone.utc),
        components=components,
    )
