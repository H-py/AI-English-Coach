"""article 模块的数据库访问层。

所有函数均为异步，并基于共享的 :class:`AsyncSession` 操作。它们负责持久化
机制（``add`` / ``flush`` / ``refresh`` / ``execute``），而事务的提交/回滚
则交由 ``get_db`` 依赖处理——后者将每个请求包裹在单个事务中。
"""

from typing import Optional

from sqlalchemy import cast, func, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.article.models import Article, Difficulty
from app.modules.article.schemas import ArticleCreate


async def get_article_by_id(
    db: AsyncSession, article_id: int
) -> Optional[Article]:
    """根据主键获取单篇文章。

    Args:
        db: 当前活跃的异步会话。
        article_id: 文章的主键。

    Returns:
        :class:`Article` 实例；若无匹配文章则返回 ``None``。
    """
    result = await db.execute(select(Article).where(Article.id == article_id))
    return result.scalars().first()


async def get_article_neighbors(
    db: AsyncSession, article_id: int
) -> tuple[Optional[tuple[int, str]], Optional[tuple[int, str]]]:
    """返回当前文章的上一篇与下一篇（循环）。

    顺序与列表接口一致：已发布文章按 ``created_at`` 倒序（最新优先），
    同时间戳时以 ``id`` 倒序保证确定性。循环规则：第一篇的上一篇是
    最后一篇，最后一篇的下一篇是第一篇。只有一篇文章时，前后都是它自身。

    Args:
        db: 当前活跃的异步会话。
        article_id: 当前文章的主键。

    Returns:
        ``(prev, next)`` 元组，每项为 ``(id, title)`` 或 ``None``。
        若文章不存在或数据库无已发布文章，两项均为 ``None``。
    """
    stmt = (
        select(Article.id, Article.title)
        .where(Article.is_published.is_(True))
        .order_by(Article.created_at.desc(), Article.id.desc())
    )
    rows = (await db.execute(stmt)).all()

    if not rows:
        return None, None

    ids = [r.id for r in rows]
    if article_id not in ids:
        return None, None

    idx = ids.index(article_id)
    n = len(ids)
    prev = rows[(idx - 1) % n]
    nxt = rows[(idx + 1) % n]
    return (prev.id, prev.title), (nxt.id, nxt.title)


async def list_articles(
    db: AsyncSession,
    difficulty: Optional[Difficulty] = None,
    cet_type: Optional[str] = None,
    tag: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Article], int]:
    """列出已发布文章，支持可选的筛选与分页。

    仅返回 ``is_published == True`` 的文章。结果按 ``created_at`` 倒序
    （最新优先）排列。

    Args:
        db: 当前活跃的异步会话。
        difficulty: 可选的难度星级筛选条件（1-5 星）。
        cet_type: 可选的四六级真题筛选条件（``'cet4'`` / ``'cet6'``）。
        tag: 可选的标签字符串筛选条件（筛选 ``tags`` JSON 数组中
            包含该标签的文章）。
        page: 从 1 开始的页码。
        page_size: 每页条数。

    Returns:
        一个 ``(items, total)`` 元组，其中 ``items`` 为请求页对应的
        :class:`Article` 实例列表，``total`` 为匹配文章的总数。
    """
    # 基础过滤条件：仅已发布文章。
    conditions = [Article.is_published.is_(True)]

    if difficulty is not None:
        conditions.append(Article.difficulty == difficulty)

    if cet_type is not None:
        conditions.append(Article.cet_type == cet_type)

    if tag is not None:
        # 将 JSON 列转换为 JSONB 并使用包含操作符（``@>``）来判断
        # tags 数组中是否包含指定标签。这是 PostgreSQL 专属的优化，
        # 可避免为标签过滤而取出全部行。
        conditions.append(
            cast(Article.tags, JSONB).contains([tag])
        )

    # 用于统计总匹配数的查询。
    count_stmt = select(func.count()).select_from(Article).where(*conditions)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # 带排序与分页的数据查询。
    offset = (page - 1) * page_size
    data_stmt = (
        select(Article)
        .where(*conditions)
        .order_by(Article.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    data_result = await db.execute(data_stmt)
    items = list(data_result.scalars().all())

    return items, total


async def create_article(
    db: AsyncSession, data: ArticleCreate, word_count: int
) -> Article:
    """创建并持久化一篇新文章。

    文章会被 flush（而非 commit），以便服务端默认值（如 ``id`` 和
    ``created_at``）被填充并出现在返回的实例上，同时外层请求事务
    仍保留提交控制权。

    Args:
        db: 当前活跃的异步会话。
        data: 已校验的创建载荷。
        word_count: 文章正文预先计算好的字数。

    Returns:
        新建的 :class:`Article`，属性已刷新。
    """
    article = Article(
        title=data.title,
        content=data.content,
        summary=data.summary,
        source=data.source,
        difficulty=data.difficulty,
        cet_type=data.cet_type,
        word_count=word_count,
        reading_time=data.reading_time,
        cover_url=data.cover_url,
        tags=data.tags,
        is_published=data.is_published,
    )
    db.add(article)
    await db.flush()
    await db.refresh(article)
    return article


async def update_article(
    db: AsyncSession, article: Article, data: dict
) -> Article:
    """对已有文章应用一组字段更新。

    仅写入 ``data`` 中出现的键。更改会被 flush，以便 ``onupdate`` 默认值
    （例如 ``updated_at``）生效，并在返回前刷新实例。

    Args:
        db: 当前活跃的异步会话。
        article: 待更新的 :class:`Article` 实例。
        data: 属性名到新值的映射。

    Returns:
        更新后的 :class:`Article`，属性已刷新。
    """
    for key, value in data.items():
        setattr(article, key, value)
    await db.flush()
    await db.refresh(article)
    return article


async def list_all_articles(
    db: AsyncSession,
    search: Optional[str] = None,
    difficulty: Optional[Difficulty] = None,
    cet_type: Optional[str] = None,
    tag: Optional[str] = None,
    is_published: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Article], int]:
    """列出全部文章（含未发布），支持可选的筛选、搜索与分页。

    供管理员使用。与 :func:`list_articles` 不同，此函数默认不会按
    ``is_published`` 过滤，使管理员可以管理草稿和未发布内容。支持
    对文章标题进行不区分大小写的子串搜索。

    Args:
        db: 当前活跃的异步会话。
        search: 可选的不区分大小写子串，用于匹配标题。
        difficulty: 可选的难度星级筛选条件（1-5 星）。
        cet_type: 可选的四六级真题筛选条件（``'cet4'`` / ``'cet6'``）。
        tag: 可选的标签字符串筛选条件（筛选 ``tags`` JSON 数组中
            包含该标签的文章）。
        is_published: 可选的发布状态筛选标志。
        page: 从 1 开始的页码。
        page_size: 每页条数。

    Returns:
        一个 ``(items, total)`` 元组，其中 ``items`` 为请求页对应的
        :class:`Article` 实例列表，``total`` 为匹配文章的总数。
    """
    conditions = []

    if search is not None and search.strip():
        conditions.append(Article.title.ilike(f"%{search}%"))

    if difficulty is not None:
        conditions.append(Article.difficulty == difficulty)

    if cet_type is not None:
        conditions.append(Article.cet_type == cet_type)

    if tag is not None:
        conditions.append(
            cast(Article.tags, JSONB).contains([tag])
        )

    if is_published is not None:
        conditions.append(Article.is_published.is_(is_published))

    # 用于统计总匹配数的查询。
    count_stmt = select(func.count()).select_from(Article).where(*conditions)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # 带排序与分页的数据查询。
    offset = (page - 1) * page_size
    data_stmt = (
        select(Article)
        .where(*conditions)
        .order_by(Article.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    data_result = await db.execute(data_stmt)
    items = list(data_result.scalars().all())

    return items, total


async def list_articles_for_recommendation(
    db: AsyncSession, cap: int = 60
) -> list[Article]:
    """按难度分层采样已发布文章，返回至多 ``cap`` 篇（难度低→高排序）。

    对每个难度（1-5 星）各取 ``ceil(cap/5)`` 篇最新文章，按 id 去重合并；
    若合并后仍不足 ``cap`` 篇，用其余最新文章补齐。保证候选清单既有难度
    多样性，又不会让推荐提示词超出 token 预算。

    Args:
        db: 当前活跃的异步会话。
        cap: 返回的最大文章数。

    Returns:
        去重后的 :class:`Article` 列表，按难度（1→5）、再按最新优先排序。
    """
    import math

    per_level = math.ceil(cap / 5)
    seen: set[int] = set()
    ordered: list[Article] = []

    # 每个难度各取 per_level 篇最新文章。
    for diff in Difficulty:
        stmt = (
            select(Article)
            .where(
                Article.is_published.is_(True),
                Article.difficulty == diff,
            )
            .order_by(Article.created_at.desc(), Article.id.desc())
            .limit(per_level)
        )
        for article in (await db.execute(stmt)).scalars().all():
            if article.id not in seen:
                seen.add(article.id)
                ordered.append(article)

    # 不足 cap 篇时，用全部已发布文章（最新优先）补齐。
    if len(ordered) < cap:
        stmt = (
            select(Article)
            .where(Article.is_published.is_(True))
            .order_by(Article.created_at.desc(), Article.id.desc())
            .limit(cap)
        )
        for article in (await db.execute(stmt)).scalars().all():
            if article.id not in seen:
                seen.add(article.id)
                ordered.append(article)

    # 难度低→高排序；同难度保持最新优先。
    ordered.sort(
        key=lambda a: (int(a.difficulty.value), -int(a.id))
    )
    return ordered[:cap]


async def delete_article(db: AsyncSession, article: Article) -> None:
    """从数据库中删除一篇文章。

    Args:
        db: 当前活跃的异步会话。
        article: 待删除的 :class:`Article` 实例。
    """
    await db.delete(article)
    await db.flush()


async def increment_view_count(
    db: AsyncSession, article_id: int
) -> None:
    """将文章的浏览次数原子性地加一。

    使用 ``UPDATE ... SET view_count = view_count + 1`` 语句，以避免
    读-改-写循环可能引发的竞态条件。

    Args:
        db: 当前活跃的异步会话。
        article_id: 文章的主键。
    """
    stmt = (
        update(Article)
        .where(Article.id == article_id)
        .values(view_count=Article.view_count + 1)
    )
    await db.execute(stmt)
    await db.flush()


async def get_all_tags(db: AsyncSession) -> list[str]:
    """返回已发布文章使用的所有唯一标签的排序列表。

    取出每篇已发布文章的 ``tags`` 列，并在 Python 中对标签去重。这样
    可以保持查询在不同数据库间的可移植性，而不依赖 PostgreSQL 专属的
    JSON 函数。

    Args:
        db: 当前活跃的异步会话。

    Returns:
        排好序的唯一标签字符串列表。
    """
    stmt = select(Article.tags).where(Article.is_published.is_(True))
    result = await db.execute(stmt)

    unique_tags: set[str] = set()
    for row in result.scalars():
        if row:
            unique_tags.update(row)
    return sorted(unique_tags)
