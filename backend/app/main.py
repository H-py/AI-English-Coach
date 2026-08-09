"""FastAPI 应用入口。

创建应用，配置由 lifespan 管理的资源（日志、MinIO 存储桶）、CORS、全局异常处理器，并挂载聚合后的 API 路由。
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
    """管理应用启动与关闭时的资源。

    启动：
        * 配置结构化日志。
        * 确保 MinIO 存储桶存在。
    关闭：
        * 关闭 Redis 连接池。
    """
    configure_logging()
    logger.info("Starting %s (env=%s)...", settings.APP_NAME, settings.APP_ENV)
    try:
        ensure_bucket()
    except Exception as exc:  # noqa: BLE001 - 记录日志但继续启动
        logger.warning("MinIO bucket check failed at startup: %s", exc)
    yield
    logger.info("Shutting down %s...", settings.APP_NAME)
    await close_redis()


def create_app() -> FastAPI:
    """应用工厂：构建并返回配置好的 FastAPI 实例。"""
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

    # ---- 异常处理器 ----
    register_exception_handlers(app)

    # ---- 路由 ----
    app.include_router(api_router)

    return app


app = create_app()
