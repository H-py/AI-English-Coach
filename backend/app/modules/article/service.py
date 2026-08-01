"""Business-logic layer for the article module.

The service sits between the HTTP routes and the repository. It owns the
domain rules: translating "not found" into a :class:`BizException`,
auto-calculating ``word_count`` from article content, and orchestrating
view-count increments on detail reads.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.modules.article.repository import (
    create_article as repo_create_article,
    delete_article as repo_delete_article,
    get_all_tags as repo_get_all_tags,
    get_article_by_id as repo_get_article_by_id,
    increment_view_count as repo_increment_view_count,
    list_articles as repo_list_articles,
    update_article as repo_update_article,
)
from app.modules.article.schemas import (
    ArticleCreate,
    ArticleListItem,
    ArticleListResponse,
    ArticleOut,
    ArticleQueryParams,
    ArticleUpdate,
)

# Business error code: the requested article does not exist.
ARTICLE_NOT_FOUND_CODE = 90002


def _calculate_word_count(content: str) -> int:
    """Calculate the word count of a text by splitting on whitespace.

    Args:
        content: The article content.

    Returns:
        The number of whitespace-separated tokens.
    """
    return len(content.split())


async def get_article_list(
    db: AsyncSession, params: ArticleQueryParams
) -> ArticleListResponse:
    """Return a paginated, filtered list of published articles.

    Args:
        db: The active async session.
        params: Query parameters for filtering (difficulty, tag) and
            pagination (page, page_size).

    Returns:
        An :class:`ArticleListResponse` with list items and page metadata.
    """
    items, total = await repo_list_articles(
        db,
        difficulty=params.difficulty,
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
    """Return the full detail of a single article and increment its views.

    Args:
        db: The active async session.
        article_id: The article's primary key.

    Returns:
        An :class:`ArticleOut` built from the persisted article.

    Raises:
        BizException: If no article exists with the given id
            (code ``90002``).
    """
    article = await repo_get_article_by_id(db, article_id)
    if article is None:
        raise BizException("article not found", code=ARTICLE_NOT_FOUND_CODE)

    # Serialize the article BEFORE incrementing the view count. The
    # ``increment_view_count`` repository method issues a Core ``UPDATE``
    # statement which causes SQLAlchemy to expire the ``article`` ORM
    # instance in the session. Accessing attributes on an expired instance
    # (as ``model_validate`` does) would trigger a lazy reload that can
    # fail if the transaction state is no longer clean. Serializing first
    # avoids this entirely; the returned ``view_count`` reflects the count
    # before this view, which is the expected behaviour.
    result = ArticleOut.model_validate(article)

    await repo_increment_view_count(db, article_id)

    return result


async def create_article(
    db: AsyncSession, data: ArticleCreate
) -> ArticleOut:
    """Create a new article with an auto-calculated word count.

    Args:
        db: The active async session.
        data: The validated create payload.

    Returns:
        An :class:`ArticleOut` for the newly created article.
    """
    word_count = _calculate_word_count(data.content)
    article = await repo_create_article(db, data, word_count)
    return ArticleOut.model_validate(article)


async def update_article(
    db: AsyncSession, article_id: int, data: ArticleUpdate
) -> ArticleOut:
    """Apply a partial update to an existing article.

    Only fields explicitly provided in ``data`` are applied (via
    ``exclude_unset``). If ``content`` is updated, ``word_count`` is
    recalculated automatically.

    Args:
        db: The active async session.
        article_id: The article's primary key.
        data: The partial update payload.

    Returns:
        An :class:`ArticleOut` reflecting the updated article.

    Raises:
        BizException: If no article exists with the given id
            (code ``90002``).
    """
    article = await repo_get_article_by_id(db, article_id)
    if article is None:
        raise BizException("article not found", code=ARTICLE_NOT_FOUND_CODE)

    update_data = data.model_dump(exclude_unset=True)

    # Recalculate word count if content is being updated.
    if "content" in update_data and update_data["content"] is not None:
        update_data["word_count"] = _calculate_word_count(
            update_data["content"]
        )

    if update_data:
        article = await repo_update_article(db, article, update_data)

    return ArticleOut.model_validate(article)


async def delete_article(db: AsyncSession, article_id: int) -> None:
    """Delete an article by its id.

    Args:
        db: The active async session.
        article_id: The article's primary key.

    Raises:
        BizException: If no article exists with the given id
            (code ``90002``).
    """
    article = await repo_get_article_by_id(db, article_id)
    if article is None:
        raise BizException("article not found", code=ARTICLE_NOT_FOUND_CODE)

    await repo_delete_article(db, article)


async def get_tags(db: AsyncSession) -> list[str]:
    """Return all unique tags used by published articles.

    Args:
        db: The active async session.

    Returns:
        A sorted list of unique tag strings.
    """
    return await repo_get_all_tags(db)
