"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import (
    ai,
    confluence,
    decision,
    health,
    history,
    indicators,
    liquidity,
    market,
    market_structure,
    multi_timeframe,
    ob_fvg,
    opportunities,
    replay,
    trade_plan,
    websocket,
)
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.security import require_auth_dependencies
from app.exchanges.manager import shutdown_exchange_manager
from app.market_data.stream_manager import get_stream_manager, shutdown_stream_manager

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application startup / shutdown hooks."""
    settings = get_settings()
    configure_logging("DEBUG" if settings.debug else "INFO")
    logger.info(
        "Starting %s v%s [%s] auth_enabled=%s",
        settings.app_name,
        __version__,
        settings.environment,
        settings.auth_enabled,
    )
    if settings.auth_enabled and (
        not settings.supabase_jwt_secret.strip() or not settings.auth_allowed_email_list
    ):
        logger.error(
            "AUTH_ENABLED=true but SUPABASE_JWT_SECRET or AUTH_ALLOWED_EMAILS is missing"
        )
    await get_stream_manager().start()
    # Optional Supabase persistence — never blocks startup when disabled/unavailable
    try:
        from app.db.session import init_db

        await init_db(settings)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Persistence init skipped: %s", exc)
    # Phase 5.5 scanner — background market opportunity scans (deterministic only)
    try:
        from app.scanner.service import get_scanner

        await get_scanner().start()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Opportunity scanner start skipped: %s", exc)
    yield
    try:
        from app.scanner.service import get_scanner

        await get_scanner().stop()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Opportunity scanner shutdown error: %s", exc)
    try:
        from app.db.session import close_db

        await close_db()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Persistence shutdown error: %s", exc)
    await shutdown_stream_manager()
    await shutdown_exchange_manager()
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    docs_on = settings.openapi_docs_enabled

    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Professional AI-powered cryptocurrency chart analysis platform. "
            "Analysis-only — does not execute real trades."
        ),
        lifespan=lifespan,
        docs_url="/docs" if docs_on else None,
        redoc_url="/redoc" if docs_on else None,
        openapi_url="/openapi.json" if docs_on else None,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health stays public for Render probes. All other application routers require auth
    # when AUTH_ENABLED=true (dependency is a no-op when auth is disabled).
    application.include_router(health.router, prefix=settings.api_v1_prefix)
    protected = require_auth_dependencies
    application.include_router(
        market.router, prefix=settings.api_v1_prefix, dependencies=protected
    )
    application.include_router(
        indicators.router, prefix=settings.api_v1_prefix, dependencies=protected
    )
    application.include_router(
        market_structure.router, prefix=settings.api_v1_prefix, dependencies=protected
    )
    application.include_router(
        liquidity.router, prefix=settings.api_v1_prefix, dependencies=protected
    )
    application.include_router(
        ob_fvg.router, prefix=settings.api_v1_prefix, dependencies=protected
    )
    application.include_router(
        multi_timeframe.router, prefix=settings.api_v1_prefix, dependencies=protected
    )
    application.include_router(
        confluence.router, prefix=settings.api_v1_prefix, dependencies=protected
    )
    application.include_router(
        trade_plan.router, prefix=settings.api_v1_prefix, dependencies=protected
    )
    application.include_router(
        decision.router, prefix=settings.api_v1_prefix, dependencies=protected
    )
    application.include_router(
        ai.router, prefix=settings.api_v1_prefix, dependencies=protected
    )
    application.include_router(
        replay.router, prefix=settings.api_v1_prefix, dependencies=protected
    )
    application.include_router(
        history.router, prefix=settings.api_v1_prefix, dependencies=protected
    )
    application.include_router(
        opportunities.router, prefix=settings.api_v1_prefix, dependencies=protected
    )
    # WebSocket routes authenticate inside the handlers (query token / Bearer).
    application.include_router(websocket.router)

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        # Do not swallow FastAPI/Starlette HTTPException responses.
        from fastapi import HTTPException
        from fastapi.exception_handlers import http_exception_handler

        if isinstance(exc, HTTPException):
            return await http_exception_handler(request, exc)

        logger.exception("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "path": str(request.url.path),
            },
        )

    @application.get("/")
    async def root() -> dict[str, str]:
        payload: dict[str, str] = {
            "service": settings.app_name,
            "version": __version__,
            "health": f"{settings.api_v1_prefix}/health",
        }
        if docs_on:
            payload["docs"] = "/docs"
        return payload

    return application


app = create_app()
