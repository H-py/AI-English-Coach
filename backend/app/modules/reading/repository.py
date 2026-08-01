"""Database access layer for the reading module.

All functions are async and operate on the shared :class:`AsyncSession`.
They perform the persistence mechanics (``add`` / ``flush`` / ``refresh`` /
``execute``) while leaving transaction commit/rollback to the ``get_db``
dependency, which wraps each request in a single transaction.
"""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.article.models import Article
from app.modules.reading.models import (
    AiConversation,
    MasteryLevel,
    ReadingHistory,
    SentenceCollection,
    WordCollection,
)
from app.modules.reading.schemas import SentenceCollectionCreate


# ---- Word collection --------------------------------------------------------


async def get_or_create_word(
    db: AsyncSession,
    user_id: int,
    word: str,
    context: str,
    article_id: Optional[int],
    ai_explanation: Optional[str],
) -> WordCollection:
    """Upsert a collected word for the user.

    If the user has already saved ``word``, the existing row is updated
    with the new ``context`` and — when a fresh explanation is supplied —
    the ``ai_explanation``. The ``article_id`` is also refreshed if a new
    one is provided. Otherwise a new :class:`WordCollection` row is
    created.

    Args:
        db: The active async session.
        user_id: The collecting user's id.
        word: The word being saved.
        context: The sentence in which the word appeared.
        article_id: The article the word came from, if any.
        ai_explanation: A pre-generated AI explanation, if any.

    Returns:
        The created or updated :class:`WordCollection`.
    """
    result = await db.execute(
        select(WordCollection).where(
            WordCollection.user_id == user_id,
            WordCollection.word == word,
        )
    )
    existing = result.scalars().first()

    if existing is not None:
        existing.context = context
        if ai_explanation is not None:
            existing.ai_explanation = ai_explanation
        if article_id is not None:
            existing.article_id = article_id
        await db.flush()
        await db.refresh(existing)
        return existing

    word_obj = WordCollection(
        user_id=user_id,
        word=word,
        context=context,
        article_id=article_id,
        ai_explanation=ai_explanation,
    )
    db.add(word_obj)
    await db.flush()
    await db.refresh(word_obj)
    return word_obj


async def list_words(
    db: AsyncSession,
    user_id: int,
    page: int,
    page_size: int,
    mastery_level: Optional[MasteryLevel] = None,
    search: Optional[str] = None,
) -> tuple[list[WordCollection], int]:
    """Return a paginated list of a user's collected words.

    Results are ordered by ``created_at`` descending (newest first).
    When ``mastery_level`` is supplied, only words at that level are
    returned. When ``search`` is supplied, only words containing the
    search string (case-insensitive) are returned.

    Args:
        db: The active async session.
        user_id: The owning user's id.
        page: The 1-based page number.
        page_size: The number of items per page.
        mastery_level: Optional filter by mastery level.
        search: Optional case-insensitive word search.

    Returns:
        A tuple of ``(items, total)``.
    """
    conditions = [WordCollection.user_id == user_id]
    if mastery_level is not None:
        conditions.append(WordCollection.mastery_level == mastery_level)
    if search:
        conditions.append(WordCollection.word.ilike(f"%{search}%"))

    count_stmt = (
        select(func.count())
        .select_from(WordCollection)
        .where(*conditions)
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    offset = (page - 1) * page_size
    data_stmt = (
        select(WordCollection)
        .where(*conditions)
        .order_by(WordCollection.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = list((await db.execute(data_stmt)).scalars().all())
    return items, total


async def get_word(
    db: AsyncSession, user_id: int, word_id: int
) -> Optional[WordCollection]:
    """Fetch a single collected word, scoped to the owning user.

    Args:
        db: The active async session.
        user_id: The owning user's id.
        word_id: The word collection's primary key.

    Returns:
        The :class:`WordCollection`, or ``None`` if not found.
    """
    result = await db.execute(
        select(WordCollection).where(
            WordCollection.id == word_id,
            WordCollection.user_id == user_id,
        )
    )
    return result.scalars().first()


async def update_word(
    db: AsyncSession, word: WordCollection, data: dict
) -> WordCollection:
    """Apply a set of field updates to an existing collected word.

    Args:
        db: The active async session.
        word: The :class:`WordCollection` instance to update.
        data: A mapping of attribute name to new value.

    Returns:
        The updated :class:`WordCollection` with refreshed attributes.
    """
    for key, value in data.items():
        setattr(word, key, value)
    await db.flush()
    await db.refresh(word)
    return word


async def delete_word(db: AsyncSession, word: WordCollection) -> None:
    """Delete a collected word from the database.

    Args:
        db: The active async session.
        word: The :class:`WordCollection` instance to delete.
    """
    await db.delete(word)
    await db.flush()


# ---- Sentence collection ----------------------------------------------------


async def create_sentence(
    db: AsyncSession, user_id: int, data: SentenceCollectionCreate
) -> SentenceCollection:
    """Create and persist a collected sentence.

    Args:
        db: The active async session.
        user_id: The collecting user's id.
        data: The validated create payload.

    Returns:
        The newly created :class:`SentenceCollection`.
    """
    sentence = SentenceCollection(
        user_id=user_id,
        sentence=data.sentence,
        article_id=data.article_id,
        note=data.note,
    )
    db.add(sentence)
    await db.flush()
    await db.refresh(sentence)
    return sentence


async def list_sentences(
    db: AsyncSession,
    user_id: int,
    page: int,
    page_size: int,
    search: Optional[str] = None,
) -> tuple[list[SentenceCollection], int]:
    """Return a paginated list of a user's collected sentences.

    Results are ordered by ``created_at`` descending (newest first).
    When ``search`` is supplied, only sentences containing the search
    string (case-insensitive) are returned.

    Args:
        db: The active async session.
        user_id: The owning user's id.
        page: The 1-based page number.
        page_size: The number of items per page.
        search: Optional case-insensitive sentence search.

    Returns:
        A tuple of ``(items, total)``.
    """
    conditions = [SentenceCollection.user_id == user_id]
    if search:
        conditions.append(SentenceCollection.sentence.ilike(f"%{search}%"))

    count_stmt = (
        select(func.count())
        .select_from(SentenceCollection)
        .where(*conditions)
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    offset = (page - 1) * page_size
    data_stmt = (
        select(SentenceCollection)
        .where(*conditions)
        .order_by(SentenceCollection.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = list((await db.execute(data_stmt)).scalars().all())
    return items, total


async def get_sentence(
    db: AsyncSession, user_id: int, sentence_id: int
) -> Optional[SentenceCollection]:
    """Fetch a single collected sentence, scoped to the owning user.

    Args:
        db: The active async session.
        user_id: The owning user's id.
        sentence_id: The sentence collection's primary key.

    Returns:
        The :class:`SentenceCollection`, or ``None`` if not found.
    """
    result = await db.execute(
        select(SentenceCollection).where(
            SentenceCollection.id == sentence_id,
            SentenceCollection.user_id == user_id,
        )
    )
    return result.scalars().first()


async def update_sentence(
    db: AsyncSession, sentence: SentenceCollection, data: dict
) -> SentenceCollection:
    """Apply field updates to an existing collected sentence.

    Args:
        db: The active async session.
        sentence: The :class:`SentenceCollection` instance to update.
        data: A mapping of attribute name to new value.

    Returns:
        The updated :class:`SentenceCollection` with refreshed attributes.
    """
    for key, value in data.items():
        setattr(sentence, key, value)
    await db.flush()
    await db.refresh(sentence)
    return sentence


async def delete_sentence(
    db: AsyncSession, sentence: SentenceCollection
) -> None:
    """Delete a collected sentence from the database.

    Args:
        db: The active async session.
        sentence: The :class:`SentenceCollection` instance to delete.
    """
    await db.delete(sentence)
    await db.flush()


# ---- Reading history --------------------------------------------------------


async def create_history(
    db: AsyncSession, user_id: int, article_id: int
) -> ReadingHistory:
    """Create and persist a new reading-history entry.

    ``started_at`` is populated by the database ``server_default``
    (``func.now()``) when the row is flushed.

    Args:
        db: The active async session.
        user_id: The reading user's id.
        article_id: The article being read.

    Returns:
        The newly created :class:`ReadingHistory`.
    """
    history = ReadingHistory(user_id=user_id, article_id=article_id)
    db.add(history)
    await db.flush()
    await db.refresh(history)
    return history


async def update_history(
    db: AsyncSession, history: ReadingHistory, data: dict
) -> ReadingHistory:
    """Apply field updates to an existing reading-history entry.

    Typically used to record ``ended_at`` and ``duration_seconds`` when a
    reading session ends.

    Args:
        db: The active async session.
        history: The :class:`ReadingHistory` instance to update.
        data: A mapping of attribute name to new value.

    Returns:
        The updated :class:`ReadingHistory` with refreshed attributes.
    """
    for key, value in data.items():
        setattr(history, key, value)
    await db.flush()
    await db.refresh(history)
    return history


async def get_history(
    db: AsyncSession, user_id: int, history_id: int
) -> Optional[ReadingHistory]:
    """Fetch a single reading-history entry, scoped to the owning user.

    Args:
        db: The active async session.
        user_id: The owning user's id.
        history_id: The history entry's primary key.

    Returns:
        The :class:`ReadingHistory`, or ``None`` if not found.
    """
    result = await db.execute(
        select(ReadingHistory).where(
            ReadingHistory.id == history_id,
            ReadingHistory.user_id == user_id,
        )
    )
    return result.scalars().first()


async def list_histories(
    db: AsyncSession, user_id: int, page: int, page_size: int
) -> tuple[list[ReadingHistory], int]:
    """Return a paginated list of a user's reading history.

    Results are ordered by ``created_at`` descending (newest first).

    Args:
        db: The active async session.
        user_id: The owning user's id.
        page: The 1-based page number.
        page_size: The number of items per page.

    Returns:
        A tuple of ``(items, total)``.
    """
    count_stmt = (
        select(func.count())
        .select_from(ReadingHistory)
        .where(ReadingHistory.user_id == user_id)
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    offset = (page - 1) * page_size
    data_stmt = (
        select(ReadingHistory)
        .where(ReadingHistory.user_id == user_id)
        .order_by(ReadingHistory.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = list((await db.execute(data_stmt)).scalars().all())
    return items, total


async def list_histories_with_article(
    db: AsyncSession, user_id: int, page: int, page_size: int
) -> tuple[list[tuple[ReadingHistory, Optional[str]]], int]:
    """Return a paginated list of reading history with article titles.

    Joins ``reading_histories`` with ``articles`` to include the article
    title for each history entry. Results are ordered by ``created_at``
    descending (newest first).

    Args:
        db: The active async session.
        user_id: The owning user's id.
        page: The 1-based page number.
        page_size: The number of items per page.

    Returns:
        A tuple of ``(items, total)`` where each item is a
        ``(ReadingHistory, article_title)`` tuple.
    """
    count_stmt = (
        select(func.count())
        .select_from(ReadingHistory)
        .where(ReadingHistory.user_id == user_id)
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    offset = (page - 1) * page_size
    data_stmt = (
        select(ReadingHistory, Article.title)
        .outerjoin(Article, ReadingHistory.article_id == Article.id)
        .where(ReadingHistory.user_id == user_id)
        .order_by(ReadingHistory.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(data_stmt)
    items = [(row[0], row[1]) for row in result.all()]
    return items, total


# ---- AI conversation --------------------------------------------------------


async def save_message(
    db: AsyncSession,
    user_id: int,
    article_id: int,
    role: str,
    content: str,
) -> AiConversation:
    """Persist a single chat message (user or assistant).

    Args:
        db: The active async session.
        user_id: The chatting user's id.
        article_id: The article the conversation is about.
        role: The message role — ``"user"`` or ``"assistant"``.
        content: The message text.

    Returns:
        The newly created :class:`AiConversation`.
    """
    message = AiConversation(
        user_id=user_id,
        article_id=article_id,
        role=role,
        content=content,
    )
    db.add(message)
    await db.flush()
    await db.refresh(message)
    return message


async def get_recent_messages(
    db: AsyncSession,
    user_id: int,
    article_id: int,
    limit: int = 10,
) -> list[AiConversation]:
    """Return the most recent chat messages for a user-article pair.

    Messages are fetched newest-first and then reversed so the returned
    list is in chronological order, ready to be used as LLM context.

    Args:
        db: The active async session.
        user_id: The chatting user's id.
        article_id: The article the conversation is about.
        limit: The maximum number of messages to return.

    Returns:
        A chronologically ordered list of :class:`AiConversation`.
    """
    stmt = (
        select(AiConversation)
        .where(
            AiConversation.user_id == user_id,
            AiConversation.article_id == article_id,
        )
        .order_by(AiConversation.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(reversed(result.scalars().all()))
