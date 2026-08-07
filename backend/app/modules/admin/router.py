"""HTTP routes for the admin module.

All endpoints require the ``AdminUser`` dependency (authenticated user with
the ``admin`` role). Routes are organised under three prefixes:

* ``/admin/dashboard`` — overview statistics
* ``/admin/articles`` — article CRUD (including unpublished content)
* ``/admin/users`` — user CRUD (with self-delete / self-demotion protection)
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
# Dashboard
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
    """Return high-level statistics for the admin overview page."""
    result = await admin_get_dashboard(db)
    return success(result)


# ---------------------------------------------------------------------------
# Article management
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
    tag: Optional[str] = Query(default=None),
    is_published: Optional[bool] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    """List all articles (including unpublished) with filtering and search."""
    params = AdminArticleQueryParams(
        search=search,
        difficulty=difficulty,
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
    """Return the full detail of an article (does not increment view count)."""
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
    """Create a new article (word count is auto-calculated)."""
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
    """Partially update an existing article."""
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
    """Delete an article by its id."""
    await admin_delete_article(db, article_id)
    return success(None)


# ---------------------------------------------------------------------------
# User management
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
    """List all users with optional filtering and search."""
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
    """Return the full detail of a single user."""
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
    """Partially update a user (role, active status, etc.)."""
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
    """Delete a user by their id (cannot delete self)."""
    await admin_delete_user(db, user_id, current_user)
    return success(None)
