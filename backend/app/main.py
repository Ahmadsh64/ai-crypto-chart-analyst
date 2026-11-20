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
    indicators,
    liquidity,
    market,
    market_structure,
    multi_timeframe,
    ob_fvg,
    replay,
    trade_plan,
    websocket,
)
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.exchanges.manager import shutdown_exchange_manager
from app.market_data.stream_manager import get_stream_manager, shutdown_stream_manager

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application startup / shutdown hooks."""
    settings = get_settings()
    configure_logging("DEBUG" if settings.debug else "INFO")
    logger.info(
        "Starting %s v%s [%s]",
        settings.app_name,
        __version__,
        settings.environment,
    )
    await get_stream_manager().start()
    yield
    await shutdown_stream_manager()
    await shutdown_exchange_manager()
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Professional AI-powered cryptocurrency chart analysis platform. "
            "Analysis-only — does not execute real trades."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health.router, prefix=settings.api_v1_prefix)
    application.include_router(market.router, prefix=settings.api_v1_prefix)
    application.include_router(indicators.router, prefix=settings.api_v1_prefix)
    application.include_router(market_structure.router, prefix=settings.api_v1_prefix)
    application.include_router(liquidity.router, prefix=settings.api_v1_prefix)
    application.include_router(ob_fvg.router, prefix=settings.api_v1_prefix)
    application.include_router(multi_timeframe.router, prefix=settings.api_v1_prefix)
    application.include_router(confluence.router, prefix=settings.api_v1_prefix)
    application.include_router(trade_plan.router, prefix=settings.api_v1_prefix)
    application.include_router(decision.router, prefix=settings.api_v1_prefix)
    application.include_router(ai.router, prefix=settings.api_v1_prefix)
    application.include_router(replay.router, prefix=settings.api_v1_prefix)
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
        return {
            "service": settings.app_name,
            "version": __version__,
            "docs": "/docs",
            "health": f"{settings.api_v1_prefix}/health",
        }

    return application


app = create_app()
