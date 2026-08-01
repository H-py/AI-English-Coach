"""Database access layer for the article module.

All functions are async and operate on the shared :class:`AsyncSession`.
They perform the persistence mechanics (``add`` / ``flush`` / ``refresh`` /
``execute``) while leaving transaction commit/rollback to the ``get_db``
dependency, which wraps each request in a single transaction.
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
    """Fetch a single article by its primary key.

    Args:
        db: The active async session.
        article_id: The article's primary key.

    Returns:
        The :class:`Article` instance, or ``None`` if no article matches.
    """
    result = await db.execute(select(Article).where(Article.id == article_id))
    return result.scalars().first()


async def list_articles(
    db: AsyncSession,
    difficulty: Optional[Difficulty] = None,
    tag: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Article], int]:
    """List published articles with optional filtering and pagination.

    Only articles with ``is_published == True`` are returned. Results are
    ordered by ``created_at`` descending (newest first).

    Args:
        db: The active async session.
        difficulty: Optional CEFR difficulty level to filter by.
        tag: Optional tag string to filter by (articles whose ``tags``
            JSON array contains the given tag).
        page: The 1-based page number.
        page_size: The number of items per page.

    Returns:
        A tuple of ``(items, total)`` where ``items`` is the list of
        :class:`Article` instances for the requested page and ``total``
        is the total count of matching articles.
    """
    # Base filter: only published articles.
    conditions = [Article.is_published.is_(True)]

    if difficulty is not None:
        conditions.append(Article.difficulty == difficulty)

    if tag is not None:
        # Cast the JSON column to JSONB and use the containment operator
        # (``@>``) to check whether the tags array contains the given tag.
        # This is a PostgreSQL-specific optimisation that avoids fetching
        # all rows for tag filtering.
        conditions.append(
            cast(Article.tags, JSONB).contains([tag])
        )

    # Count query for total matches.
    count_stmt = select(func.count()).select_from(Article).where(*conditions)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Data query with ordering and pagination.
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
    """Create and persist a new article.

    The article is flushed (not committed) so that server-side defaults
    such as ``id`` and ``created_at`` are populated and available on the
    returned instance, while the outer request transaction retains commit
    control.

    Args:
        db: The active async session.
        data: The validated create payload.
        word_count: The pre-computed word count for the article content.

    Returns:
        The newly created :class:`Article` with refreshed attributes.
    """
    article = Article(
        title=data.title,
        content=data.content,
        summary=data.summary,
        source=data.source,
        difficulty=data.difficulty,
        word_count=word_count,
        reading_time=data.reading_time,
        cover_url=data.cover_url,
        tags=data.tags,
        is_published=True,
    )
    db.add(article)
    await db.flush()
    await db.refresh(article)
    return article


async def update_article(
    db: AsyncSession, article: Article, data: dict
) -> Article:
    """Apply a set of field updates to an existing article.

    Only the keys present in ``data`` are written. The changes are flushed
    so that ``onupdate`` defaults (e.g. ``updated_at``) take effect, and
    the instance is refreshed before being returned.

    Args:
        db: The active async session.
        article: The :class:`Article` instance to update.
        data: A mapping of attribute name to new value.

    Returns:
        The updated :class:`Article` with refreshed attributes.
    """
    for key, value in data.items():
        setattr(article, key, value)
    await db.flush()
    await db.refresh(article)
    return article


async def delete_article(db: AsyncSession, article: Article) -> None:
    """Delete an article from the database.

    Args:
        db: The active async session.
        article: The :class:`Article` instance to delete.
    """
    await db.delete(article)
    await db.flush()


async def increment_view_count(
    db: AsyncSession, article_id: int
) -> None:
    """Atomically increment the view count of an article by one.

    Uses an ``UPDATE ... SET view_count = view_count + 1`` statement to
    avoid race conditions that could arise from a read-modify-write cycle.

    Args:
        db: The active async session.
        article_id: The article's primary key.
    """
    stmt = (
        update(Article)
        .where(Article.id == article_id)
        .values(view_count=Article.view_count + 1)
    )
    await db.execute(stmt)
    await db.flush()


async def get_all_tags(db: AsyncSession) -> list[str]:
    """Return a sorted list of all unique tags used by published articles.

    Fetches the ``tags`` column for every published article and deduplicates
    the tag values in Python. This keeps the query portable across databases
    rather than relying on PostgreSQL-specific JSON functions.

    Args:
        db: The active async session.

    Returns:
        A sorted list of unique tag strings.
    """
    stmt = select(Article.tags).where(Article.is_published.is_(True))
    result = await db.execute(stmt)

    unique_tags: set[str] = set()
    for row in result.scalars():
        if row:
            unique_tags.update(row)
    return sorted(unique_tags)
