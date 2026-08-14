"""article 模块的业务逻辑层。

服务层位于 HTTP 路由与 repository 之间，负责领域规则：将“未找到”转换为
:class:`BizException`、根据文章正文自动计算 ``word_count``，并在详情读取时
编排浏览次数的自增。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.modules.article.repository import (
    create_article as repo_create_article,
    delete_article as repo_delete_article,
    get_all_tags as repo_get_all_tags,
    get_article_by_id as repo_get_article_by_id,
    get_article_neighbors as repo_get_article_neighbors,
    increment_view_count as repo_increment_view_count,
    list_articles as repo_list_articles,
    update_article as repo_update_article,
)
from app.modules.article.schemas import (
    ArticleCreate,
    ArticleListItem,
    ArticleListResponse,
    ArticleNeighborRef,
    ArticleNeighborsOut,
    ArticleOut,
    ArticleQueryParams,
    ArticleUpdate,
)

# 业务错误码：请求的文章不存在。
ARTICLE_NOT_FOUND_CODE = 90002


def _calculate_word_count(content: str) -> int:
    """通过按空白字符拆分文本来计算单词数。

    Args:
        content: 文章正文。

    Returns:
        按空白字符拆分后的 token 数量。
    """
    return len(content.split())


async def get_article_list(
    db: AsyncSession, params: ArticleQueryParams
) -> ArticleListResponse:
    """返回已发布文章的分页、筛选列表。

    Args:
        db: 当前活跃的异步会话。
        params: 用于筛选（difficulty、tag）和分页（page、page_size）
            的查询参数。

    Returns:
        一个 :class:`ArticleListResponse`，包含列表项与分页元数据。
    """
    items, total = await repo_list_articles(
        db,
        difficulty=params.difficulty,
        cet_type=params.cet_type,
        tag=params.tag,
        page=params.page,
        page_size=params.page_size,
    )
    return ArticleListResponse(
        items=[ArticleListItem.model_validate(article) for article in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


async def get_article_detail(
    db: AsyncSession, article_id: int
) -> ArticleOut:
    """返回单篇文章的完整详情，并增加其浏览次数。

    Args:
        db: 当前活跃的异步会话。
        article_id: 文章的主键。

    Returns:
        由持久化文章构建的 :class:`ArticleOut`。

    Raises:
        BizException: 如果不存在指定 id 的文章
            （错误码 ``90002``）。
    """
    article = await repo_get_article_by_id(db, article_id)
    if article is None:
        raise BizException("article not found", code=ARTICLE_NOT_FOUND_CODE)

    # 在增加浏览次数之前先序列化文章。``increment_view_count`` repository
    # 方法会发出一条 Core ``UPDATE`` 语句，这会导致 SQLAlchemy 让会话中
    # 的 ``article`` ORM 实例过期。在过期实例上访问属性（正如
    # ``model_validate`` 所做的那样）会触发一次懒加载，而当事务状态不再
    # 干净时该懒加载可能会失败。先序列化可以完全规避这一问题；返回的
    # ``view_count`` 反映的是本次浏览之前的次数，这正是预期行为。
    result = ArticleOut.model_validate(article)

    await repo_increment_view_count(db, article_id)

    return result


async def get_article_neighbors(
    db: AsyncSession, article_id: int
) -> ArticleNeighborsOut:
    """返回当前文章的上一篇 / 下一篇（循环）。

    顺序与列表接口一致（``created_at`` 倒序）。循环规则：第一篇的
    上一篇是最后一篇，最后一篇的下一篇是第一篇。

    Args:
        db: 当前活跃的异步会话。
        article_id: 当前文章的主键。

    Returns:
        :class:`ArticleNeighborsOut`，包含 ``prev`` 与 ``next`` 的
        轻量引用（可能为 ``None``）。

    Raises:
        BizException: 如果不存在指定 id 的文章
            （错误码 ``90002``）。
    """
    article = await repo_get_article_by_id(db, article_id)
    if article is None:
        raise BizException("article not found", code=ARTICLE_NOT_FOUND_CODE)

    prev, nxt = await repo_get_article_neighbors(db, article_id)
    return ArticleNeighborsOut(
        prev=ArticleNeighborRef(id=prev[0], title=prev[1]) if prev else None,
        next=ArticleNeighborRef(id=nxt[0], title=nxt[1]) if nxt else None,
    )


async def create_article(
    db: AsyncSession, data: ArticleCreate
) -> ArticleOut:
    """创建新文章，并自动计算字数。

    Args:
        db: 当前活跃的异步会话。
        data: 已校验的创建载荷。

    Returns:
        新建文章对应的 :class:`ArticleOut`。
    """
    word_count = _calculate_word_count(data.content)
    article = await repo_create_article(db, data, word_count)
    return ArticleOut.model_validate(article)


async def update_article(
    db: AsyncSession, article_id: int, data: ArticleUpdate
) -> ArticleOut:
    """对已有文章应用部分更新。

    仅应用 ``data`` 中显式提供的字段（通过 ``exclude_unset``）。若
    ``content`` 被更新，``word_count`` 会自动重新计算。

    Args:
        db: 当前活跃的异步会话。
        article_id: 文章的主键。
        data: 部分更新载荷。

    Returns:
        反映更新后文章的 :class:`ArticleOut`。

    Raises:
        BizException: 如果不存在指定 id 的文章
            （错误码 ``90002``）。
    """
    article = await repo_get_article_by_id(db, article_id)
    if article is None:
        raise BizException("article not found", code=ARTICLE_NOT_FOUND_CODE)

    update_data = data.model_dump(exclude_unset=True)

    # 若正文正在更新，则重新计算字数。
    if "content" in update_data and update_data["content"] is not None:
        update_data["word_count"] = _calculate_word_count(
            update_data["content"]
        )

    if update_data:
        article = await repo_update_article(db, article, update_data)

    return ArticleOut.model_validate(article)


async def delete_article(db: AsyncSession, article_id: int) -> None:
    """根据 id 删除文章。

    Args:
        db: 当前活跃的异步会话。
        article_id: 文章的主键。

    Raises:
        BizException: 如果不存在指定 id 的文章
            （错误码 ``90002``）。
    """
    article = await repo_get_article_by_id(db, article_id)
    if article is None:
        raise BizException("article not found", code=ARTICLE_NOT_FOUND_CODE)

    await repo_delete_article(db, article)


async def get_tags(db: AsyncSession) -> list[str]:
    """返回已发布文章使用的所有唯一标签。

    Args:
        db: 当前活跃的异步会话。

    Returns:
        排好序的唯一标签字符串列表。
    """
    return await repo_get_all_tags(db)
