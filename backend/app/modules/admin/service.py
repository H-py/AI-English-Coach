"""Business-logic layer for the admin module.

Provides admin-only operations for article management, user management, and
dashboard statistics. Article CRUD reuses the existing article repository
functions but adds admin-specific behaviour (e.g. listing unpublished
articles, fetching detail without incrementing view count). User management
includes self-delete protection to prevent administrators from locking
themselves out.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.modules.admin.schemas import (
    AdminArticleListItem,
    AdminArticleListResponse,
    AdminArticleQueryParams,
    AdminDashboard,
    AdminUserListResponse,
    AdminUserOut,
    AdminUserQueryParams,
    AdminUserUpdate,
)
from app.modules.article.models import Article
from app.modules.article.repository import (
    create_article as repo_create_article,
    delete_article as repo_delete_article,
    get_article_by_id as repo_get_article_by_id,
    list_all_articles as repo_list_all_articles,
    update_article as repo_update_article,
)
from app.modules.article.schemas import ArticleCreate, ArticleOut, ArticleUpdate
from app.modules.users.models import User, UserRole
from app.modules.users.repository import (
    delete_user as repo_delete_user,
    get_user_by_id as repo_get_user_by_id,
    list_users as repo_list_users,
    update_user as repo_update_user,
)

# Reused business error codes.
ARTICLE_NOT_FOUND_CODE = 90002
USER_NOT_FOUND_CODE = 90001

# Admin-specific error codes.
CANNOT_DELETE_SELF_CODE = 20006
CANNOT_DEMOTE_LAST_ADMIN_CODE = 20007


def _calculate_word_count(content: str) -> int:
    """Calculate the word count of a text by splitting on whitespace."""
    return len(content.split())


# ---------------------------------------------------------------------------
# Article management
# ---------------------------------------------------------------------------

async def admin_list_articles(
    db: AsyncSession, params: AdminArticleQueryParams
) -> AdminArticleListResponse:
    """Return a paginated, filtered list of all articles (including drafts)."""
    items, total = await repo_list_all_articles(
        db,
        search=params.search,
        difficulty=params.difficulty,
        tag=params.tag,
        is_published=params.is_published,
        page=params.page,
        page_size=params.page_size,
    )
    return AdminArticleListResponse(
        items=[AdminArticleListItem.model_validate(article) for article in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


async def admin_get_article(
    db: AsyncSession, article_id: int
) -> ArticleOut:
    """Return the full detail of an article without incrementing view count.

    Unlike the public :func:`get_article_detail`, this function does not
    bump ``view_count`` — administrators should be able to inspect articles
    without skewing analytics.

    Raises:
        BizException: If no article exists with the given id.
    """
    article = await repo_get_article_by_id(db, article_id)
    if article is None:
        raise BizException("article not found", code=ARTICLE_NOT_FOUND_CODE)
    return ArticleOut.model_validate(article)


async def admin_create_article(
    db: AsyncSession, data: ArticleCreate
) -> ArticleOut:
    """Create a new article with an auto-calculated word count."""
    word_count = _calculate_word_count(data.content)
    article = await repo_create_article(db, data, word_count)
    return ArticleOut.model_validate(article)


async def admin_update_article(
    db: AsyncSession, article_id: int, data: ArticleUpdate
) -> ArticleOut:
    """Apply a partial update to an existing article."""
    article = await repo_get_article_by_id(db, article_id)
    if article is None:
        raise BizException("article not found", code=ARTICLE_NOT_FOUND_CODE)

    update_data = data.model_dump(exclude_unset=True)

    if "content" in update_data and update_data["content"] is not None:
        update_data["word_count"] = _calculate_word_count(
            update_data["content"]
        )

    if update_data:
        article = await repo_update_article(db, article, update_data)

    return ArticleOut.model_validate(article)


async def admin_delete_article(db: AsyncSession, article_id: int) -> None:
    """Delete an article by its id."""
    article = await repo_get_article_by_id(db, article_id)
    if article is None:
        raise BizException("article not found", code=ARTICLE_NOT_FOUND_CODE)
    await repo_delete_article(db, article)


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

async def admin_list_users(
    db: AsyncSession, params: AdminUserQueryParams
) -> AdminUserListResponse:
    """Return a paginated, filtered list of all users."""
    items, total = await repo_list_users(
        db,
        search=params.search,
        role=params.role,
        is_active=params.is_active,
        page=params.page,
        page_size=params.page_size,
    )
    return AdminUserListResponse(
        items=[AdminUserOut.model_validate(user) for user in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


async def admin_get_user(db: AsyncSession, user_id: int) -> AdminUserOut:
    """Return the full detail of a single user.

    Raises:
        BizException: If no user exists with the given id.
    """
    user = await repo_get_user_by_id(db, user_id)
    if user is None:
        raise BizException("user not found", code=USER_NOT_FOUND_CODE)
    return AdminUserOut.model_validate(user)


async def admin_update_user(
    db: AsyncSession, user_id: int, data: AdminUserUpdate, current_user: User
) -> AdminUserOut:
    """Apply a partial update to an existing user.

    Prevents the current admin from demoting themselves (which could lock
    them out if they are the only admin).

    Raises:
        BizException: If the user is not found, or if the current admin
            attempts to demote themselves.
    """
    user = await repo_get_user_by_id(db, user_id)
    if user is None:
        raise BizException("user not found", code=USER_NOT_FOUND_CODE)

    update_data = data.model_dump(exclude_unset=True)

    # Prevent self-demotion: an admin cannot remove their own admin role.
    if (
        user_id == current_user.id
        and "role" in update_data
        and update_data["role"] != UserRole.admin
    ):
        raise BizException(
            "cannot demote yourself: ask another admin to change your role",
            code=CANNOT_DEMOTE_LAST_ADMIN_CODE,
            http_status=403,
        )

    if update_data:
        user = await repo_update_user(db, user, update_data)

    return AdminUserOut.model_validate(user)


async def admin_delete_user(
    db: AsyncSession, user_id: int, current_user: User
) -> None:
    """Delete a user by their id.

    Prevents self-deletion to avoid accidental lockout.

    Raises:
        BizException: If the user is not found, or if the current admin
            attempts to delete their own account.
    """
    if user_id == current_user.id:
        raise BizException(
            "cannot delete your own account",
            code=CANNOT_DELETE_SELF_CODE,
            http_status=403,
        )

    user = await repo_get_user_by_id(db, user_id)
    if user is None:
        raise BizException("user not found", code=USER_NOT_FOUND_CODE)

    await repo_delete_user(db, user)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

async def admin_get_dashboard(db: AsyncSession) -> AdminDashboard:
    """Return high-level statistics for the admin overview page."""
    total_users = await db.scalar(
        select(func.count()).select_from(User)
    ) or 0

    total_articles = await db.scalar(
        select(func.count()).select_from(Article)
    ) or 0

    published_articles = await db.scalar(
        select(func.count()).select_from(Article).where(
            Article.is_published.is_(True)
        )
    ) or 0

    total_views = await db.scalar(
        select(func.coalesce(func.sum(Article.view_count), 0))
    ) or 0

    return AdminDashboard(
        total_users=total_users,
        total_articles=total_articles,
        published_articles=published_articles,
        total_views=total_views,
    )
