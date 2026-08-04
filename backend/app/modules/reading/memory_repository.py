"""Database access layer for AI memory and user profile tables.

All functions are async and operate on the shared :class:`AsyncSession`.
They handle persistence mechanics (``add`` / ``flush`` / ``refresh`` /
``execute``) while leaving transaction commit/rollback to the ``get_db``
dependency.
"""

from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reading.models import AiConversation, AiMemory, UserProfile


# ---- Unsummarized messages (short-term memory source) ----------------------


async def get_unsummarized_messages(
    db: AsyncSession, user_id: int, article_id: int
) -> list[AiConversation]:
    """Return all unsummarized messages for a user-article pair.

    Messages are ordered by ``id`` ascending (chronological) so the
    caller can easily split off the oldest batch for summarization.

    Args:
        db: The active async session.
        user_id: The chatting user's id.
        article_id: The article the conversation is about.

    Returns:
        A chronologically ordered list of unsummarized
        :class:`AiConversation` messages.
    """
    stmt = (
        select(AiConversation)
        .where(
            AiConversation.user_id == user_id,
            AiConversation.article_id == article_id,
            AiConversation.is_summarized.is_(False),
        )
        .order_by(AiConversation.id.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def mark_messages_summarized(
    db: AsyncSession, message_ids: list[int]
) -> None:
    """Mark a batch of messages as summarized.

    Args:
        db: The active async session.
        message_ids: The ids of the messages to mark.
    """
    if not message_ids:
        return
    await db.execute(
        update(AiConversation)
        .where(AiConversation.id.in_(message_ids))
        .values(is_summarized=True)
    )
    await db.flush()


async def count_unsummarized_tokens(
    db: AsyncSession, user_id: int, article_id: int
) -> int:
    """Count the total tokens of unsummarized messages.

    Uses the database's ``LENGTH`` function as a rough character proxy;
    the caller converts to an estimated token count. This avoids loading
    all message bodies into Python just to count them.

    Args:
        db: The active async session.
        user_id: The chatting user's id.
        article_id: The article the conversation is about.

    Returns:
        The total character count of unsummarized message content.
    """
    stmt = (
        select(func.coalesce(func.sum(func.length(AiConversation.content)), 0))
        .where(
            AiConversation.user_id == user_id,
            AiConversation.article_id == article_id,
            AiConversation.is_summarized.is_(False),
        )
    )
    result = await db.execute(stmt)
    return result.scalar() or 0


# ---- AI memories (long-term memory) ----------------------------------------


async def create_memory(
    db: AsyncSession,
    user_id: int,
    article_id: Optional[int],
    memory_type: str,
    content: str,
    importance: float,
    token_count: int,
) -> AiMemory:
    """Create a new long-term memory entry.

    Args:
        db: The active async session.
        user_id: The owning user's id.
        article_id: The related article, or ``None`` for global memories.
        memory_type: One of ``summary`` / ``fact`` / ``mistake`` /
            ``preference``.
        content: The memory text (LLM-generated summary or fact).
        importance: A 0.0-1.0 importance score.
        token_count: The estimated token count of ``content``.

    Returns:
        The newly created :class:`AiMemory`.
    """
    memory = AiMemory(
        user_id=user_id,
        article_id=article_id,
        memory_type=memory_type,
        content=content,
        importance=importance,
        token_count=token_count,
    )
    db.add(memory)
    await db.flush()
    await db.refresh(memory)
    return memory


async def get_active_memories(
    db: AsyncSession, user_id: int, max_tokens: int = 2000
) -> list[AiMemory]:
    """Load the most relevant active memories for a user.

    Memories are ordered by ``importance`` descending so the most
    significant ones are loaded first. The function accumulates memories
    until the token budget is exhausted.

    Global memories (``article_id IS NULL``) are always included; article-
    specific memories are loaded only when the caller passes the article
    id via the separate :func:`get_active_article_memories` function.

    Args:
        db: The active async session.
        user_id: The owning user's id.
        max_tokens: The maximum total token budget for loaded memories.

    Returns:
        A list of :class:`AiMemory` entries, most important first.
    """
    stmt = (
        select(AiMemory)
        .where(
            AiMemory.user_id == user_id,
            AiMemory.is_active.is_(True),
            AiMemory.article_id.is_(None),
        )
        .order_by(AiMemory.importance.desc())
    )
    result = await db.execute(stmt)
    all_memories = list(result.scalars().all())

    selected: list[AiMemory] = []
    used_tokens = 0
    for mem in all_memories:
        if used_tokens + mem.token_count > max_tokens:
            continue
        selected.append(mem)
        used_tokens += mem.token_count

    return selected


async def get_active_article_memories(
    db: AsyncSession, user_id: int, article_id: int, max_tokens: int = 1000
) -> list[AiMemory]:
    """Load article-specific active memories for a user.

    Similar to :func:`get_active_memories` but scoped to a specific
    article.

    Args:
        db: The active async session.
        user_id: The owning user's id.
        article_id: The article to load memories for.
        max_tokens: The maximum total token budget.

    Returns:
        A list of :class:`AiMemory` entries, most important first.
    """
    stmt = (
        select(AiMemory)
        .where(
            AiMemory.user_id == user_id,
            AiMemory.article_id == article_id,
            AiMemory.is_active.is_(True),
        )
        .order_by(AiMemory.importance.desc())
    )
    result = await db.execute(stmt)
    all_memories = list(result.scalars().all())

    selected: list[AiMemory] = []
    used_tokens = 0
    for mem in all_memories:
        if used_tokens + mem.token_count > max_tokens:
            continue
        selected.append(mem)
        used_tokens += mem.token_count

    return selected


async def get_all_active_memories(
    db: AsyncSession, user_id: int, max_tokens: int = 4000
) -> list[AiMemory]:
    """Load all active memories for a user, regardless of article scope.

    Combines both global (``article_id IS NULL``) and article-specific
    memories into a single list, ordered by ``importance`` descending.
    Used by the profile generator so it can synthesize the user's
    learning profile from the full conversation history across all
    articles.

    Args:
        db: The active async session.
        user_id: The owning user's id.
        max_tokens: The maximum total token budget for loaded memories.

    Returns:
        A list of :class:`AiMemory` entries, most important first.
    """
    stmt = (
        select(AiMemory)
        .where(
            AiMemory.user_id == user_id,
            AiMemory.is_active.is_(True),
        )
        .order_by(AiMemory.importance.desc())
    )
    result = await db.execute(stmt)
    all_memories = list(result.scalars().all())

    selected: list[AiMemory] = []
    used_tokens = 0
    for mem in all_memories:
        if used_tokens + mem.token_count > max_tokens:
            continue
        selected.append(mem)
        used_tokens += mem.token_count

    return selected


async def count_memories(
    db: AsyncSession, user_id: int, article_id: Optional[int] = None
) -> int:
    """Count active memories for a user, optionally scoped to an article.

    Used to decide whether a profile refresh should be triggered.

    Args:
        db: The active async session.
        user_id: The owning user's id.
        article_id: Optional article scope.

    Returns:
        The number of active memory entries.
    """
    conditions = [
        AiMemory.user_id == user_id,
        AiMemory.is_active.is_(True),
    ]
    if article_id is not None:
        conditions.append(AiMemory.article_id == article_id)

    stmt = select(func.count()).select_from(AiMemory).where(*conditions)
    result = await db.execute(stmt)
    return result.scalar() or 0


async def deactivate_article_memories(
    db: AsyncSession, user_id: int, article_id: int
) -> None:
    """Mark all article-specific memories as inactive.

    Called when a new summary replaces old ones for the same article.

    Args:
        db: The active async session.
        user_id: The owning user's id.
        article_id: The article whose memories to deactivate.
    """
    await db.execute(
        update(AiMemory)
        .where(
            AiMemory.user_id == user_id,
            AiMemory.article_id == article_id,
            AiMemory.memory_type == "summary",
            AiMemory.is_active.is_(True),
        )
        .values(is_active=False)
    )
    await db.flush()


async def deactivate_global_facts(
    db: AsyncSession, user_id: int
) -> None:
    """Mark all active global fact memories as inactive.

    Called before creating a new user traits entry so that only the
    latest traits remain active (``article_id IS NULL`` and
    ``memory_type = 'fact'``). This prevents duplicate user trait
    records from accumulating across summarization cycles.

    Args:
        db: The active async session.
        user_id: The owning user's id.
    """
    await db.execute(
        update(AiMemory)
        .where(
            AiMemory.user_id == user_id,
            AiMemory.article_id.is_(None),
            AiMemory.memory_type == "fact",
            AiMemory.is_active.is_(True),
        )
        .values(is_active=False)
    )
    await db.flush()


# ---- User profiles ---------------------------------------------------------


async def get_profile(
    db: AsyncSession, user_id: int
) -> Optional[UserProfile]:
    """Fetch a user's profile, or ``None`` if not yet created.

    Args:
        db: The active async session.
        user_id: The user's id.

    Returns:
        The :class:`UserProfile`, or ``None``.
    """
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    return result.scalars().first()


async def upsert_profile(
    db: AsyncSession,
    user_id: int,
    profile_summary: str,
    strengths: list[str],
    weaknesses: list[str],
    learning_style: Optional[str],
    interests: list[str],
    common_mistakes: list[str],
    message_count: int,
) -> UserProfile:
    """Create or update a user's profile.

    Args:
        db: The active async session.
        user_id: The user's id.
        profile_summary: The natural-language profile text.
        strengths: List of user strengths.
        weaknesses: List of user weaknesses.
        learning_style: The user's learning style.
        interests: List of interest topics.
        common_mistakes: List of recurring mistakes.
        message_count: The total message count at this update.

    Returns:
        The created or updated :class:`UserProfile`.
    """
    existing = await get_profile(db, user_id)

    if existing is not None:
        existing.profile_summary = profile_summary
        existing.strengths = strengths
        existing.weaknesses = weaknesses
        existing.learning_style = learning_style
        existing.interests = interests
        existing.common_mistakes = common_mistakes
        existing.message_count = message_count
        existing.last_updated_at = func.now()
        await db.flush()
        await db.refresh(existing)
        return existing

    profile = UserProfile(
        user_id=user_id,
        profile_summary=profile_summary,
        strengths=strengths,
        weaknesses=weaknesses,
        learning_style=learning_style,
        interests=interests,
        common_mistakes=common_mistakes,
        message_count=message_count,
        last_updated_at=func.now(),
    )
    db.add(profile)
    await db.flush()
    await db.refresh(profile)
    return profile


async def increment_message_count(
    db: AsyncSession, user_id: int, delta: int = 1
) -> None:
    """Increment the message count on a user's profile.

    Creates a profile row with defaults if one does not exist yet.

    Args:
        db: The active async session.
        user_id: The user's id.
        delta: The increment amount (default 1).
    """
    existing = await get_profile(db, user_id)
    if existing is not None:
        existing.message_count += delta
        await db.flush()
    else:
        # Create a stub profile that will be filled in later.
        profile = UserProfile(
            user_id=user_id,
            message_count=delta,
        )
        db.add(profile)
        await db.flush()
