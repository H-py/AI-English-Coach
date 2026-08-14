"""admin 模块的 HTTP 路由。

所有端点都需要 ``AdminUser`` 依赖（即已认证且具备 ``admin`` 角色的用户）。
路由按三个前缀组织：

* ``/admin/dashboard`` —— 概览统计
* ``/admin/articles`` —— 文章增删改查（包含未发布内容）
* ``/admin/users`` —— 用户增删改查（包含禁止自删 / 禁止自我降级保护）
"""

from typing import Optional

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, DbSession
from app.core.response import ResponseModel, success
from app.modules.admin.schemas import (
    AdminArticleListResponse,
    AdminArticleQueryParams,
    AdminDashboard,
    AdminUserListResponse,
    AdminUserOut,
    AdminUserQueryParams,
    AdminUserUpdate,
)
from app.modules.admin.service import (
    admin_create_article,
    admin_delete_article,
    admin_delete_user,
    admin_get_article,
    admin_get_dashboard,
    admin_get_user,
    admin_list_articles,
    admin_list_users,
    admin_update_article,
    admin_update_user,
)
from app.modules.article.models import Difficulty
from app.modules.article.schemas import ArticleCreate, ArticleOut, ArticleUpdate
from app.modules.users.models import UserRole

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# 仪表盘
# ---------------------------------------------------------------------------

@router.get(
    "/dashboard",
    response_model=ResponseModel[AdminDashboard],
    summary="Admin dashboard statistics",
)
async def get_dashboard(
    db: DbSession,
    _: AdminUser,
) -> dict:
    """返回管理概览页面的高层统计数据。"""
    result = await admin_get_dashboard(db)
    return success(result)


# ---------------------------------------------------------------------------
# 文章管理
# ---------------------------------------------------------------------------

@router.get(
    "/articles",
    response_model=ResponseModel[AdminArticleListResponse],
    summary="List all articles (admin)",
)
async def list_articles_endpoint(
    db: DbSession,
    _: AdminUser,
    search: Optional[str] = Query(default=None),
    difficulty: Optional[Difficulty] = Query(default=None),
    cet_type: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    is_published: Optional[bool] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    """列出所有文章（包含未发布），支持筛选与搜索。"""
    params = AdminArticleQueryParams(
        search=search,
        difficulty=difficulty,
        cet_type=cet_type,
        tag=tag,
        is_published=is_published,
        page=page,
        page_size=page_size,
    )
    result = await admin_list_articles(db, params)
    return success(result)


@router.get(
    "/articles/{article_id}",
    response_model=ResponseModel[ArticleOut],
    summary="Get article detail (admin)",
)
async def get_article_endpoint(
    article_id: int,
    db: DbSession,
    _: AdminUser,
) -> dict:
    """返回文章的完整详情（不会增加浏览次数）。"""
    result = await admin_get_article(db, article_id)
    return success(result)


@router.post(
    "/articles",
    response_model=ResponseModel[ArticleOut],
    status_code=201,
    summary="Create article (admin)",
)
async def create_article_endpoint(
    data: ArticleCreate,
    db: DbSession,
    _: AdminUser,
) -> dict:
    """创建新文章（字数会自动计算）。"""
    result = await admin_create_article(db, data)
    return success(result)


@router.put(
    "/articles/{article_id}",
    response_model=ResponseModel[ArticleOut],
    summary="Update article (admin)",
)
async def update_article_endpoint(
    article_id: int,
    data: ArticleUpdate,
    db: DbSession,
    _: AdminUser,
) -> dict:
    """对已有文章进行部分更新。"""
    result = await admin_update_article(db, article_id, data)
    return success(result)


@router.delete(
    "/articles/{article_id}",
    response_model=ResponseModel[None],
    summary="Delete article (admin)",
)
async def delete_article_endpoint(
    article_id: int,
    db: DbSession,
    _: AdminUser,
) -> dict:
    """根据 id 删除文章。"""
    await admin_delete_article(db, article_id)
    return success(None)


# ---------------------------------------------------------------------------
# 用户管理
# ---------------------------------------------------------------------------

@router.get(
    "/users",
    response_model=ResponseModel[AdminUserListResponse],
    summary="List all users (admin)",
)
async def list_users_endpoint(
    db: DbSession,
    _: AdminUser,
    search: Optional[str] = Query(default=None),
    role: Optional[UserRole] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    """列出所有用户，支持可选的筛选与搜索。"""
    params = AdminUserQueryParams(
        search=search,
        role=role,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )
    result = await admin_list_users(db, params)
    return success(result)


@router.get(
    "/users/{user_id}",
    response_model=ResponseModel[AdminUserOut],
    summary="Get user detail (admin)",
)
async def get_user_endpoint(
    user_id: int,
    db: DbSession,
    _: AdminUser,
) -> dict:
    """返回单个用户的完整详情。"""
    result = await admin_get_user(db, user_id)
    return success(result)


@router.put(
    "/users/{user_id}",
    response_model=ResponseModel[AdminUserOut],
    summary="Update user (admin)",
)
async def update_user_endpoint(
    user_id: int,
    data: AdminUserUpdate,
    db: DbSession,
    current_user: AdminUser,
) -> dict:
    """对用户进行部分更新（角色、启用状态等）。"""
    result = await admin_update_user(db, user_id, data, current_user)
    return success(result)


@router.delete(
    "/users/{user_id}",
    response_model=ResponseModel[None],
    summary="Delete user (admin)",
)
async def delete_user_endpoint(
    user_id: int,
    db: DbSession,
    current_user: AdminUser,
) -> dict:
    """根据 id 删除用户（不能删除自己）。"""
    await admin_delete_user(db, user_id, current_user)
    return success(None)
