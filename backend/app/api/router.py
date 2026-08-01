"""Top-level API router aggregation.

All feature-module routers are included here under the shared ``/api/v1``
prefix, giving the frontend a single, stable base URL of
``http://localhost:8000/api/v1``.
"""

from fastapi import APIRouter

from app.modules.article.router import router as article_router
from app.modules.auth.router import router as auth_router
from app.modules.health.router import router as health_router
from app.modules.reading.router import router as reading_router
from app.modules.users.router import router as users_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(article_router)
api_router.include_router(reading_router)

__all__ = ["api_router"]
