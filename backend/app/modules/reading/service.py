"""Business-logic layer for the reading module.

The service sits between the HTTP routes and the repository. It owns the
domain rules: validating article existence, building LLM prompts with the
right context, streaming AI responses back to the caller, and persisting
word/sentence collections and reading history.

AI-interaction methods (``explain_word``, ``analyze_sentence``,
``paragraph_summary``, ``chat``) are async generators that yield ``str``
chunks from the LLM provider's streaming endpoint. The router wraps these
into Server-Sent Events. The ``chat`` method additionally persists both
the user's message and the full assistant reply after streaming finishes.
"""

from collections.abc import AsyncGenerator
from typing import Optional

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai.cache import (
    cache_key,
    get_cached_response,
    set_cached_response,
)
from app.core.ai.factory import get_llm_provider
from app.core.ai.memory import build_chat_context, maybe_summarize
from app.core.ai.prompt_manager import load_reading_prompt, load_system_prompt
from app.core.ai.provider import ChatMessage
from app.core.exceptions import BizException
from app.modules.article.models import Article
from app.modules.article.repository import get_article_by_id
from app.modules.reading import memory_repository as mem_repo
from app.modules.reading import repository as repo
from app.modules.reading.models import MasteryLevel
from app.modules.reading.schemas import (
    AnalyzeSentenceRequest,
    ChatRequest,
    ConversationListResponse,
    ConversationOut,
    ExplainWordRequest,
    ParagraphSummaryRequest,
    ReadingHistoryCreate,
    ReadingHistoryListResponse,
    ReadingHistoryOut,
    ReadingHistoryUpdate,
    ReadingHistoryWithArticleListResponse,
    ReadingHistoryWithArticleOut,
    SentenceCollectionCreate,
    SentenceCollectionOut,
    SentenceCollectionUpdate,
    SentenceListResponse,
    SentenceTranslationRequest,
    WordCollectionCreate,
    WordCollectionOut,
    WordCollectionUpdate,
    WordListResponse,
)
from app.modules.users.models import User

# ---- Business error codes ---------------------------------------------------
# Article not found (shared with the article module's code).
ARTICLE_NOT_FOUND_CODE = 90002
# Collected word not found for the current user.
WORD_NOT_FOUND_CODE = 90003
# Collected sentence not found for the current user.
SENTENCE_NOT_FOUND_CODE = 90004
# Reading-history entry not found for the current user.
HISTORY_NOT_FOUND_CODE = 90005

# ---- Per-endpoint LLM parameters --------------------------------------------
# Temperature and max_tokens are tuned per endpoint based on the desired
# output style: deterministic for translation/analysis, creative for chat.
_TEMP_EXPLAIN_WORD = 0.5      # balanced — needs some variety for examples
_TEMP_ANALYZE_SENTENCE = 0.3  # deterministic — grammar analysis should be stable
_TEMP_TRANSLATE_SENTENCE = 0.3  # deterministic — translations should be consistent
_TEMP_PARAGRAPH_SUMMARY = 0.5  # moderately deterministic — summaries should be stable
_TEMP_CHAT = 0.8              # more creative — conversational, flexible answers

_MAX_TOKENS_EXPLAIN_WORD = 500
_MAX_TOKENS_ANALYZE_SENTENCE = 800
_MAX_TOKENS_TRANSLATE_SENTENCE = 600
_MAX_TOKENS_PARAGRAPH_SUMMARY = 400
_MAX_TOKENS_CHAT = 1000


async def _get_article_or_raise(
    db: AsyncSession, article_id: int
) -> Article:
    """Fetch an article by id or raise a not-found business exception.

    Args:
        db: The active async session.
        article_id: The article's primary key.

    Returns:
        The :class:`~app.modules.article.models.Article` instance.

    Raises:
        BizException: If no article exists with the given id
            (code ``90002``).
    """
    article = await get_article_by_id(db, article_id)
    if article is None:
        raise BizException("article not found", code=ARTICLE_NOT_FOUND_CODE)
    return article


# ---- AI streaming services --------------------------------------------------


async def explain_word(
    db: AsyncSession, user: User, data: ExplainWordRequest,
    redis: aioredis.Redis,
) -> AsyncGenerator[str, None]:
    """Stream an AI explanation of a word in context.

    Checks Redis cache first — the same word in the same context for the
    same English level always produces the same explanation, so a cache
    hit returns instantly with zero API cost. On cache miss, the response
    is streamed from the LLM, accumulated, and stored in Redis for future
    requests.

    Args:
        db: The active async session.
        user: The authenticated user (used for English level).
        data: The explain-word request payload.
        redis: The shared Redis client for response caching.

    Yields:
        ``str`` chunks of the LLM response.
    """
    await _get_article_or_raise(db, data.article_id)

    level = user.english_level.value
    ckey = cache_key("explain-word", level, data.word, data.context)

    # Cache hit — replay as a single chunk.
    cached = await get_cached_response(redis, ckey)
    if cached is not None:
        yield cached
        return

    # Cache miss — stream from LLM and cache the full response.
    system_prompt = load_system_prompt("coach")
    user_prompt = load_reading_prompt(
        "explain_word",
        word=data.word,
        context=data.context,
        level=level,
    )
    messages = [
        ChatMessage("system", system_prompt),
        ChatMessage("user", user_prompt),
    ]

    provider = get_llm_provider()
    collected: list[str] = []
    async for chunk in provider.chat_stream(
        messages, temperature=_TEMP_EXPLAIN_WORD,
        max_tokens=_MAX_TOKENS_EXPLAIN_WORD,
    ):
        collected.append(chunk)
        yield chunk

    await set_cached_response(redis, ckey, "".join(collected))


async def analyze_sentence(
    db: AsyncSession, user: User, data: AnalyzeSentenceRequest,
    redis: aioredis.Redis,
) -> AsyncGenerator[str, None]:
    """Stream an AI structural analysis of a sentence.

    Results are cached in Redis — the same sentence for the same English
    level always yields the same analysis. On cache hit the stored
    response is replayed instantly without calling the LLM.

    Args:
        db: The active async session.
        user: The authenticated user (used for English level).
        data: The analyze-sentence request payload.
        redis: The shared Redis client for response caching.

    Yields:
        ``str`` chunks of the LLM response.
    """
    await _get_article_or_raise(db, data.article_id)

    level = user.english_level.value
    ckey = cache_key("analyze-sentence", level, data.sentence)

    cached = await get_cached_response(redis, ckey)
    if cached is not None:
        yield cached
        return

    system_prompt = load_system_prompt("coach")
    user_prompt = load_reading_prompt(
        "sentence_analysis",
        sentence=data.sentence,
        level=level,
    )
    messages = [
        ChatMessage("system", system_prompt),
        ChatMessage("user", user_prompt),
    ]

    provider = get_llm_provider()
    collected: list[str] = []
    async for chunk in provider.chat_stream(
        messages, temperature=_TEMP_ANALYZE_SENTENCE,
        max_tokens=_MAX_TOKENS_ANALYZE_SENTENCE,
    ):
        collected.append(chunk)
        yield chunk

    await set_cached_response(redis, ckey, "".join(collected))


async def translate_sentence(
    db: AsyncSession, user: User, data: SentenceTranslationRequest,
    redis: aioredis.Redis,
) -> AsyncGenerator[str, None]:
    """Stream an AI translation of a sentence into Chinese.

    Results are cached in Redis — the same sentence for the same English
    level always yields the same translation.

    Args:
        db: The active async session.
        user: The authenticated user (used for English level).
        data: The translation request payload.
        redis: The shared Redis client for response caching.

    Yields:
        ``str`` chunks of the LLM response.
    """
    await _get_article_or_raise(db, data.article_id)

    level = user.english_level.value
    ckey = cache_key("translate-sentence", level, data.sentence)

    cached = await get_cached_response(redis, ckey)
    if cached is not None:
        yield cached
        return

    system_prompt = load_system_prompt("coach")
    user_prompt = load_reading_prompt(
        "sentence_translation",
        sentence=data.sentence,
        level=level,
    )
    messages = [
        ChatMessage("system", system_prompt),
        ChatMessage("user", user_prompt),
    ]

    provider = get_llm_provider()
    collected: list[str] = []
    async for chunk in provider.chat_stream(
        messages, temperature=_TEMP_TRANSLATE_SENTENCE,
        max_tokens=_MAX_TOKENS_TRANSLATE_SENTENCE,
    ):
        collected.append(chunk)
        yield chunk

    await set_cached_response(redis, ckey, "".join(collected))


async def paragraph_summary(
    db: AsyncSession, user: User, data: ParagraphSummaryRequest,
    redis: aioredis.Redis,
) -> AsyncGenerator[str, None]:
    """Stream an AI summary of a paragraph.

    Results are cached in Redis — the same paragraph for the same English
    level always yields the same summary.

    Args:
        db: The active async session.
        user: The authenticated user (used for English level).
        data: The paragraph-summary request payload.
        redis: The shared Redis client for response caching.

    Yields:
        ``str`` chunks of the LLM response.
    """
    await _get_article_or_raise(db, data.article_id)

    level = user.english_level.value
    ckey = cache_key("paragraph-summary", level, data.paragraph)

    cached = await get_cached_response(redis, ckey)
    if cached is not None:
        yield cached
        return

    system_prompt = load_system_prompt("coach")
    user_prompt = load_reading_prompt(
        "paragraph_summary",
        paragraph=data.paragraph,
        level=level,
    )
    messages = [
        ChatMessage("system", system_prompt),
        ChatMessage("user", user_prompt),
    ]

    provider = get_llm_provider()
    collected: list[str] = []
    async for chunk in provider.chat_stream(
        messages, temperature=_TEMP_PARAGRAPH_SUMMARY,
        max_tokens=_MAX_TOKENS_PARAGRAPH_SUMMARY,
    ):
        collected.append(chunk)
        yield chunk

    await set_cached_response(redis, ckey, "".join(collected))


async def chat(
    db: AsyncSession, user: User, data: ChatRequest,
    redis: aioredis.Redis,
) -> AsyncGenerator[str, None]:
    """Stream an AI chat reply about the current article.

    Uses the three-layer memory system (:mod:`app.core.ai.memory`) to
    assemble context:

    - **Long-term memory** (user profile + compressed summaries) is
      loaded from Redis cache (or DB on miss) and injected into the
      system prompt.
    - **Short-term memory** (unsummarized conversation messages) is
      loaded from the database and trimmed to fit the remaining token
      budget.
    - The user's new message is appended last.

    After streaming completes, both the user's message and the full
    assistant reply are persisted. Then ``maybe_summarize`` checks
    whether the oldest unsummarized messages should be compressed into
    a long-term memory entry.

    Args:
        db: The active async session.
        user: The authenticated user.
        data: The chat request payload.
        redis: The shared Redis client for memory caching.

    Yields:
        ``str`` chunks of the LLM response.
    """
    article = await _get_article_or_raise(db, data.article_id)

    # Build the full context with three-layer memory.
    messages = await build_chat_context(
        db, redis, user, article, data.message
    )

    provider = get_llm_provider()
    collected: list[str] = []
    async for chunk in provider.chat_stream(
        messages, temperature=_TEMP_CHAT, max_tokens=_MAX_TOKENS_CHAT,
    ):
        collected.append(chunk)
        yield chunk

    # Persist the full conversation after streaming finishes.
    await repo.save_message(db, user.id, data.article_id, "user", data.message)
    await repo.save_message(
        db, user.id, data.article_id, "assistant", "".join(collected)
    )

    # Increment the user's message count for profile tracking.
    await mem_repo.increment_message_count(db, user.id, delta=2)

    # Trigger summarization if unsummarized messages exceed the threshold.
    await maybe_summarize(db, redis, user.id, data.article_id)


# ---- Word collection services ----------------------------------------------


async def save_word(
    db: AsyncSession, user_id: int, data: WordCollectionCreate
) -> WordCollectionOut:
    """Save (upsert) a collected word for the user.

    Args:
        db: The active async session.
        user_id: The collecting user's id.
        data: The word-collection create payload.

    Returns:
        A :class:`WordCollectionOut` for the created or updated word.
    """
    word = await repo.get_or_create_word(
        db,
        user_id=user_id,
        word=data.word,
        context=data.context,
        article_id=data.article_id,
        ai_explanation=data.ai_explanation,
    )
    return WordCollectionOut.model_validate(word)


async def list_words(
    db: AsyncSession,
    user_id: int,
    page: int,
    page_size: int,
    mastery_level: Optional[MasteryLevel] = None,
    search: Optional[str] = None,
) -> WordListResponse:
    """Return a paginated list of the user's collected words.

    Args:
        db: The active async session.
        user_id: The owning user's id.
        page: The 1-based page number.
        page_size: The number of items per page.
        mastery_level: Optional filter by mastery level.
        search: Optional case-insensitive word search.

    Returns:
        A :class:`WordListResponse` with serialized items and total.
    """
    items, total = await repo.list_words(
        db, user_id, page, page_size, mastery_level, search
    )
    return WordListResponse(
        items=[WordCollectionOut.model_validate(w) for w in items],
        total=total,
    )


async def update_word_mastery(
    db: AsyncSession,
    user_id: int,
    word_id: int,
    data: WordCollectionUpdate,
) -> WordCollectionOut:
    """Update the mastery level and/or study count of a collected word.

    Args:
        db: The active async session.
        user_id: The owning user's id.
        word_id: The word collection's primary key.
        data: The partial update payload.

    Returns:
        A :class:`WordCollectionOut` reflecting the updated word.

    Raises:
        BizException: If no word exists with the given id for the user
            (code ``90003``).
    """
    word = await repo.get_word(db, user_id, word_id)
    if word is None:
        raise BizException("word not found", code=WORD_NOT_FOUND_CODE)

    update_data = data.model_dump(exclude_unset=True)
    if update_data:
        word = await repo.update_word(db, word, update_data)
    return WordCollectionOut.model_validate(word)


async def remove_word(db: AsyncSession, user_id: int, word_id: int) -> None:
    """Delete a collected word.

    Args:
        db: The active async session.
        user_id: The owning user's id.
        word_id: The word collection's primary key.

    Raises:
        BizException: If no word exists with the given id for the user
            (code ``90003``).
    """
    word = await repo.get_word(db, user_id, word_id)
    if word is None:
        raise BizException("word not found", code=WORD_NOT_FOUND_CODE)
    await repo.delete_word(db, word)


# ---- Sentence collection services ------------------------------------------


async def save_sentence(
    db: AsyncSession, user_id: int, data: SentenceCollectionCreate
) -> SentenceCollectionOut:
    """Save (upsert) a collected sentence for the user.

    If the same sentence text already exists for this user, the existing
    row's note and article_id are updated instead of creating a duplicate.

    Args:
        db: The active async session.
        user_id: The collecting user's id.
        data: The sentence-collection create payload.

    Returns:
        A :class:`SentenceCollectionOut` for the created or updated sentence.
    """
    sentence = await repo.get_or_create_sentence(db, user_id, data)
    return SentenceCollectionOut.model_validate(sentence)


async def list_sentences(
    db: AsyncSession,
    user_id: int,
    page: int,
    page_size: int,
    search: Optional[str] = None,
) -> SentenceListResponse:
    """Return a paginated list of the user's collected sentences.

    Args:
        db: The active async session.
        user_id: The owning user's id.
        page: The 1-based page number.
        page_size: The number of items per page.
        search: Optional case-insensitive sentence search.

    Returns:
        A :class:`SentenceListResponse` with serialized items and total.
    """
    items, total = await repo.list_sentences(
        db, user_id, page, page_size, search
    )
    return SentenceListResponse(
        items=[SentenceCollectionOut.model_validate(s) for s in items],
        total=total,
    )


async def remove_sentence(
    db: AsyncSession, user_id: int, sentence_id: int
) -> None:
    """Delete a collected sentence.

    Args:
        db: The active async session.
        user_id: The owning user's id.
        sentence_id: The sentence collection's primary key.

    Raises:
        BizException: If no sentence exists with the given id for the
            user (code ``90004``).
    """
    sentence = await repo.get_sentence(db, user_id, sentence_id)
    if sentence is None:
        raise BizException("sentence not found", code=SENTENCE_NOT_FOUND_CODE)
    await repo.delete_sentence(db, sentence)


async def update_sentence_note(
    db: AsyncSession,
    user_id: int,
    sentence_id: int,
    data: SentenceCollectionUpdate,
) -> SentenceCollectionOut:
    """Update the note on a collected sentence.

    Args:
        db: The active async session.
        user_id: The owning user's id.
        sentence_id: The sentence collection's primary key.
        data: The partial update payload (``note``).

    Returns:
        A :class:`SentenceCollectionOut` reflecting the updated sentence.

    Raises:
        BizException: If no sentence exists with the given id for the
            user (code ``90004``).
    """
    sentence = await repo.get_sentence(db, user_id, sentence_id)
    if sentence is None:
        raise BizException("sentence not found", code=SENTENCE_NOT_FOUND_CODE)

    update_data = data.model_dump(exclude_unset=True)
    if update_data:
        sentence = await repo.update_sentence(db, sentence, update_data)
    return SentenceCollectionOut.model_validate(sentence)


# ---- Reading history services ----------------------------------------------


async def start_reading(
    db: AsyncSession, user_id: int, data: ReadingHistoryCreate
) -> ReadingHistoryOut:
    """Start (or resume) a reading session for an article.

    Validates that the article exists. If the user already has a history
    row for this article, ``read_count`` is incremented and the session
    timestamps are reset for the new reading. Otherwise a new row is
    created.

    Args:
        db: The active async session.
        user_id: The reading user's id.
        data: The reading-history create payload.

    Returns:
        A :class:`ReadingHistoryOut` for the created or updated entry.

    Raises:
        BizException: If the article does not exist (code ``90002``).
    """
    await _get_article_or_raise(db, data.article_id)
    history = await repo.get_or_create_history(db, user_id, data.article_id)
    return ReadingHistoryOut.model_validate(history)


async def end_reading(
    db: AsyncSession,
    user_id: int,
    history_id: int,
    data: ReadingHistoryUpdate,
) -> ReadingHistoryOut:
    """End a reading session, recording the end time and duration.

    Args:
        db: The active async session.
        user_id: The owning user's id.
        history_id: The reading-history entry's primary key.
        data: The partial update payload (``ended_at`` / ``duration_seconds``).

    Returns:
        A :class:`ReadingHistoryOut` reflecting the updated entry.

    Raises:
        BizException: If no history entry exists with the given id for
            the user (code ``90005``).
    """
    history = await repo.get_history(db, user_id, history_id)
    if history is None:
        raise BizException("history not found", code=HISTORY_NOT_FOUND_CODE)

    update_data = data.model_dump(exclude_unset=True)
    if update_data:
        history = await repo.update_history(db, history, update_data)
    return ReadingHistoryOut.model_validate(history)


async def list_histories(
    db: AsyncSession, user_id: int, page: int, page_size: int
) -> ReadingHistoryWithArticleListResponse:
    """Return a paginated list of the user's reading history.

    Each entry is enriched with the article title via a join, so the
    client can display which article was read without a second request.

    Args:
        db: The active async session.
        user_id: The owning user's id.
        page: The 1-based page number.
        page_size: The number of items per page.

    Returns:
        A :class:`ReadingHistoryWithArticleListResponse` with serialized
        items (including ``article_title``) and total.
    """
    items, total = await repo.list_histories_with_article(
        db, user_id, page, page_size
    )
    serialized: list[ReadingHistoryWithArticleOut] = []
    for history, article_title in items:
        obj = ReadingHistoryWithArticleOut.model_validate(history)
        obj.article_title = article_title
        serialized.append(obj)
    return ReadingHistoryWithArticleListResponse(
        items=serialized,
        total=total,
    )


# ---- AI conversation services -----------------------------------------------


async def list_conversations(
    db: AsyncSession, user_id: int, article_id: int
) -> ConversationListResponse:
    """Return the user's AI chat history for a specific article.

    Loads up to 50 most recent messages in chronological order so the
    frontend can restore a chat session after a page refresh. The
    article must exist.

    Args:
        db: The active async session.
        user_id: The chatting user's id.
        article_id: The article whose conversation history to load.

    Returns:
        A :class:`ConversationListResponse` with serialized messages.

    Raises:
        BizException: If the article does not exist (code ``90002``).
    """
    await _get_article_or_raise(db, article_id)
    messages = await repo.list_conversations(db, user_id, article_id)
    return ConversationListResponse(
        items=[ConversationOut.model_validate(m) for m in messages],
        total=len(messages),
    )
