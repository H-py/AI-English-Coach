"""顶层 API 路由聚合。

所有功能模块的路由都在此处被挂载到共享的 ``/api/v1`` 前缀下，使前端
拥有一个单一、稳定的基础 URL：``http://localhost:8000/api/v1``。
"""

from fastapi import APIRouter

from app.modules.admin.router import router as admin_router
from app.modules.ai.router import router as ai_router
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
api_router.include_router(ai_router)
api_router.include_router(admin_router)

__all__ = ["api_router"]
