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

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai.factory import get_llm_provider
from app.core.ai.prompt_manager import load_reading_prompt, load_system_prompt
from app.core.ai.provider import ChatMessage
from app.core.exceptions import BizException
from app.modules.article.models import Article
from app.modules.article.repository import get_article_by_id
from app.modules.reading import repository as repo
from app.modules.reading.models import MasteryLevel
from app.modules.reading.schemas import (
    AnalyzeSentenceRequest,
    ChatRequest,
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
    db: AsyncSession, user: User, data: ExplainWordRequest
) -> AsyncGenerator[str, None]:
    """Stream an AI explanation of a word in context.

    Validates that the referenced article exists, then builds a system
    prompt (the coach persona) and a user prompt (the ``explain_word``
    template) parameterised by the user's English level, and streams the
    LLM response chunk by chunk.

    Args:
        db: The active async session.
        user: The authenticated user (used for English level).
        data: The explain-word request payload.

    Yields:
        ``str`` chunks of the LLM response.
    """
    await _get_article_or_raise(db, data.article_id)

    system_prompt = load_system_prompt("coach")
    user_prompt = load_reading_prompt(
        "explain_word",
        word=data.word,
        context=data.context,
        level=user.english_level.value,
    )
    messages = [
        ChatMessage("system", system_prompt),
        ChatMessage("user", user_prompt),
    ]

    provider = get_llm_provider()
    async for chunk in provider.chat_stream(messages):
        yield chunk


async def analyze_sentence(
    db: AsyncSession, user: User, data: AnalyzeSentenceRequest
) -> AsyncGenerator[str, None]:
    """Stream an AI structural analysis of a sentence.

    Args:
        db: The active async session.
        user: The authenticated user (used for English level).
        data: The analyze-sentence request payload.

    Yields:
        ``str`` chunks of the LLM response.
    """
    await _get_article_or_raise(db, data.article_id)

    system_prompt = load_system_prompt("coach")
    user_prompt = load_reading_prompt(
        "sentence_analysis",
        sentence=data.sentence,
        level=user.english_level.value,
    )
    messages = [
        ChatMessage("system", system_prompt),
        ChatMessage("user", user_prompt),
    ]

    provider = get_llm_provider()
    async for chunk in provider.chat_stream(messages):
        yield chunk


async def translate_sentence(
    db: AsyncSession, user: User, data: SentenceTranslationRequest
) -> AsyncGenerator[str, None]:
    """Stream an AI translation of a sentence into Chinese.

    Args:
        db: The active async session.
        user: The authenticated user (used for English level).
        data: The translation request payload.

    Yields:
        ``str`` chunks of the LLM response.
    """
    await _get_article_or_raise(db, data.article_id)

    system_prompt = load_system_prompt("coach")
    user_prompt = load_reading_prompt(
        "sentence_translation",
        sentence=data.sentence,
        level=user.english_level.value,
    )
    messages = [
        ChatMessage("system", system_prompt),
        ChatMessage("user", user_prompt),
    ]

    provider = get_llm_provider()
    async for chunk in provider.chat_stream(messages):
        yield chunk


async def paragraph_summary(
    db: AsyncSession, user: User, data: ParagraphSummaryRequest
) -> AsyncGenerator[str, None]:
    """Stream an AI summary of a paragraph.

    Args:
        db: The active async session.
        user: The authenticated user (used for English level).
        data: The paragraph-summary request payload.

    Yields:
        ``str`` chunks of the LLM response.
    """
    await _get_article_or_raise(db, data.article_id)

    system_prompt = load_system_prompt("coach")
    user_prompt = load_reading_prompt(
        "paragraph_summary",
        paragraph=data.paragraph,
        level=user.english_level.value,
    )
    messages = [
        ChatMessage("system", system_prompt),
        ChatMessage("user", user_prompt),
    ]

    provider = get_llm_provider()
    async for chunk in provider.chat_stream(messages):
        yield chunk


async def chat(
    db: AsyncSession, user: User, data: ChatRequest
) -> AsyncGenerator[str, None]:
    """Stream an AI chat reply about the current article.

    Loads the article's title and content plus the most recent
    conversation messages as context, streams the assistant reply, and
    then persists both the user's message and the full assistant reply
    to ``ai_conversations`` so that future turns can reference them.

    The assistant reply text is accumulated while streaming so it can be
    saved in full after the stream completes. Persistence happens only
    on successful completion — if streaming fails mid-way, neither
    message is saved.

    Args:
        db: The active async session.
        user: The authenticated user.
        data: The chat request payload.

    Yields:
        ``str`` chunks of the LLM response.
    """
    article = await _get_article_or_raise(db, data.article_id)

    recent = await repo.get_recent_messages(
        db, user.id, data.article_id, limit=10
    )

    system_prompt = load_reading_prompt(
        "chat", title=article.title, content=article.content
    )
    messages: list[ChatMessage] = [ChatMessage("system", system_prompt)]
    for msg in recent:
        messages.append(ChatMessage(msg.role, msg.content))
    messages.append(ChatMessage("user", data.message))

    provider = get_llm_provider()
    collected: list[str] = []
    async for chunk in provider.chat_stream(messages):
        collected.append(chunk)
        yield chunk

    # Persist the full conversation after streaming finishes.
    await repo.save_message(db, user.id, data.article_id, "user", data.message)
    await repo.save_message(
        db, user.id, data.article_id, "assistant", "".join(collected)
    )


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
    """Save a collected sentence for the user.

    Args:
        db: The active async session.
        user_id: The collecting user's id.
        data: The sentence-collection create payload.

    Returns:
        A :class:`SentenceCollectionOut` for the created sentence.
    """
    sentence = await repo.create_sentence(db, user_id, data)
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
    """Start a new reading session for an article.

    Validates that the article exists before creating the history entry.

    Args:
        db: The active async session.
        user_id: The reading user's id.
        data: The reading-history create payload.

    Returns:
        A :class:`ReadingHistoryOut` for the created entry.

    Raises:
        BizException: If the article does not exist (code ``90002``).
    """
    await _get_article_or_raise(db, data.article_id)
    history = await repo.create_history(db, user_id, data.article_id)
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
