"""FastAPI application entry point.

Creates the app, configures lifespan-managed resources (logging, MinIO
bucket), CORS, global exception handlers, and mounts the aggregated API
router.
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.redis import close_redis
from app.core.storage import ensure_bucket

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown resources.

    Startup:
        * Configure structured logging.
        * Ensure the MinIO bucket exists.
    Shutdown:
        * Close the Redis connection pool.
    """
    configure_logging()
    logger.info("Starting %s (env=%s)...", settings.APP_NAME, settings.APP_ENV)
    try:
        ensure_bucket()
    except Exception as exc:  # noqa: BLE001 - log but continue booting
        logger.warning("MinIO bucket check failed at startup: %s", exc)
    yield
    logger.info("Shutting down %s...", settings.APP_NAME)
    await close_redis()


def create_app() -> FastAPI:
    """Application factory: build and return the configured FastAPI instance."""
    app = FastAPI(
        title=settings.APP_NAME,
        description="AI-powered English reading coach platform API.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ---- CORS ----
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Exception handlers ----
    register_exception_handlers(app)

    # ---- Routes ----
    app.include_router(api_router)

    return app


app = create_app()
