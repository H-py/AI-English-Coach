"""admin 模块的业务逻辑层。

提供文章管理、用户管理和仪表盘统计等仅管理员可用的操作。文章增删改查复用
现有的 article repository 函数，但增加了管理员专属行为（例如列出未发布
文章、获取详情时不增加浏览次数）。用户管理包含禁止自删保护，以防止管理员
把自己锁在系统之外。
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

# 复用的业务错误码。
ARTICLE_NOT_FOUND_CODE = 90002
USER_NOT_FOUND_CODE = 90001

# admin 专属错误码。
CANNOT_DELETE_SELF_CODE = 20006
CANNOT_DEMOTE_LAST_ADMIN_CODE = 20007


def _calculate_word_count(content: str) -> int:
    """通过按空白字符拆分文本来计算单词数。"""
    return len(content.split())


# ---------------------------------------------------------------------------
# 文章管理
# ---------------------------------------------------------------------------

async def admin_list_articles(
    db: AsyncSession, params: AdminArticleQueryParams
) -> AdminArticleListResponse:
    """返回所有文章（含草稿）的分页、筛选列表。"""
    items, total = await repo_list_all_articles(
        db,
        search=params.search,
        difficulty=params.difficulty,
        cet_type=params.cet_type,
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
    """返回文章的完整详情，且不增加浏览次数。

    与公开的 :func:`get_article_detail` 不同，此函数不会自增 ``view_count``
    ——管理员应能在不影响分析数据的前提下审阅文章。

    Raises:
        BizException: 如果不存在指定 id 的文章。
    """
    article = await repo_get_article_by_id(db, article_id)
    if article is None:
        raise BizException("article not found", code=ARTICLE_NOT_FOUND_CODE)
    return ArticleOut.model_validate(article)


async def admin_create_article(
    db: AsyncSession, data: ArticleCreate
) -> ArticleOut:
    """创建新文章，并自动计算字数。"""
    word_count = _calculate_word_count(data.content)
    article = await repo_create_article(db, data, word_count)
    return ArticleOut.model_validate(article)


async def admin_update_article(
    db: AsyncSession, article_id: int, data: ArticleUpdate
) -> ArticleOut:
    """对已有文章应用部分更新。"""
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
    """根据 id 删除文章。"""
    article = await repo_get_article_by_id(db, article_id)
    if article is None:
        raise BizException("article not found", code=ARTICLE_NOT_FOUND_CODE)
    await repo_delete_article(db, article)


# ---------------------------------------------------------------------------
# 用户管理
# ---------------------------------------------------------------------------

async def admin_list_users(
    db: AsyncSession, params: AdminUserQueryParams
) -> AdminUserListResponse:
    """返回所有用户的分页、筛选列表。"""
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
    """返回单个用户的完整详情。

    Raises:
        BizException: 如果不存在指定 id 的用户。
    """
    user = await repo_get_user_by_id(db, user_id)
    if user is None:
        raise BizException("user not found", code=USER_NOT_FOUND_CODE)
    return AdminUserOut.model_validate(user)


async def admin_update_user(
    db: AsyncSession, user_id: int, data: AdminUserUpdate, current_user: User
) -> AdminUserOut:
    """对已有用户应用部分更新。

    阻止当前管理员自我降级（若其是唯一管理员，自我降级会导致自身被锁在系统外）。

    Raises:
        BizException: 如果用户不存在，或当前管理员试图自我降级。
    """
    user = await repo_get_user_by_id(db, user_id)
    if user is None:
        raise BizException("user not found", code=USER_NOT_FOUND_CODE)

    update_data = data.model_dump(exclude_unset=True)

    # 阻止自我降级：管理员不能移除自己的管理员角色。
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
    """根据 id 删除用户。

    阻止自我删除，以免意外被锁在系统外。

    Raises:
        BizException: 如果用户不存在，或当前管理员试图删除自己的账号。
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
# 仪表盘
# ---------------------------------------------------------------------------

async def admin_get_dashboard(db: AsyncSession) -> AdminDashboard:
    """返回管理概览页面的高层统计数据。"""
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
