"""HTTP routes for the reading module.

Provides four AI streaming endpoints (Server-Sent Events) for word
explanation, sentence analysis, paragraph summary, and article chat,
plus standard REST endpoints for word collections, sentence collections,
and reading history. All endpoints require authentication.

SSE protocol
-------------
Each streaming endpoint emits ``text/event-stream`` frames of the form::

    data: {"content": "<chunk>"}\\n\\n

When the stream completes normally a terminal frame is sent::

    data: {"done": true}\\n\\n

If an error occurs during streaming, an error frame is sent instead::

    data: {"error": "<message>"}\\n\\n
"""

import json
from collections.abc import AsyncGenerator
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession, RedisClient
from app.core.exceptions import BizException
from app.core.response import ResponseModel, success
from app.modules.reading.models import MasteryLevel
from app.modules.reading.schemas import (
    AnalyzeSentenceRequest,
    ChatRequest,
    ConversationListResponse,
    ExplainWordRequest,
    ParagraphSummaryRequest,
    ReadingHistoryCreate,
    ReadingHistoryOut,
    ReadingHistoryUpdate,
    ReadingHistoryWithArticleListResponse,
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
from app.modules.reading.service import (
    analyze_sentence,
    chat,
    end_reading,
    explain_word,
    list_conversations,
    list_histories,
    list_sentences,
    list_words,
    paragraph_summary,
    remove_sentence,
    remove_word,
    save_sentence,
    save_word,
    start_reading,
    translate_sentence,
    update_sentence_note,
    update_word_mastery,
)

router = APIRouter(prefix="/reading", tags=["reading"])


# ---- SSE helper -------------------------------------------------------------


def _sse_stream(
    generator: AsyncGenerator[str, None],
) -> AsyncGenerator[str, None]:
    """Wrap a service async generator into an SSE byte stream.

    Each yielded chunk is framed as ``data: {"content": ...}\\n\\n``. On
    normal completion a ``data: {"done": true}\\n\\n`` frame is emitted.
    :class:`BizException` instances produce ``data: {"error": ...}\\n\\n``
    using the exception's message; any other exception uses ``str(exc)``.

    Args:
        generator: The service-layer async generator yielding ``str``
            chunks.

    Yields:
        SSE-formatted ``str`` frames.
    """

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            async for chunk in generator:
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except BizException as e:
            yield f"data: {json.dumps({'error': e.message})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return event_stream()


# ---- AI streaming endpoints (SSE) ------------------------------------------


@router.post(
    "/explain-word",
    summary="Explain a word in context (streaming)",
)
async def explain_word_endpoint(
    data: ExplainWordRequest,
    db: DbSession,
    current_user: CurrentUser,
    redis: RedisClient,
) -> StreamingResponse:
    """Stream an AI explanation of a word as Server-Sent Events."""
    return StreamingResponse(
        _sse_stream(explain_word(db, current_user, data, redis)),
        media_type="text/event-stream",
    )


@router.post(
    "/analyze-sentence",
    summary="Analyze a sentence structure (streaming)",
)
async def analyze_sentence_endpoint(
    data: AnalyzeSentenceRequest,
    db: DbSession,
    current_user: CurrentUser,
    redis: RedisClient,
) -> StreamingResponse:
    """Stream an AI structural analysis of a sentence as Server-Sent Events."""
    return StreamingResponse(
        _sse_stream(analyze_sentence(db, current_user, data, redis)),
        media_type="text/event-stream",
    )


@router.post(
    "/translate-sentence",
    summary="Translate a sentence into Chinese (streaming)",
)
async def translate_sentence_endpoint(
    data: SentenceTranslationRequest,
    db: DbSession,
    current_user: CurrentUser,
    redis: RedisClient,
) -> StreamingResponse:
    """Stream an AI translation of a sentence as Server-Sent Events."""
    return StreamingResponse(
        _sse_stream(translate_sentence(db, current_user, data, redis)),
        media_type="text/event-stream",
    )


@router.post(
    "/paragraph-summary",
    summary="Summarize a paragraph (streaming)",
)
async def paragraph_summary_endpoint(
    data: ParagraphSummaryRequest,
    db: DbSession,
    current_user: CurrentUser,
    redis: RedisClient,
) -> StreamingResponse:
    """Stream an AI summary of a paragraph as Server-Sent Events."""
    return StreamingResponse(
        _sse_stream(paragraph_summary(db, current_user, data, redis)),
        media_type="text/event-stream",
    )


@router.post(
    "/chat",
    summary="Chat about the current article (streaming)",
)
async def chat_endpoint(
    data: ChatRequest,
    db: DbSession,
    current_user: CurrentUser,
    redis: RedisClient,
) -> StreamingResponse:
    """Stream an AI chat reply about the current article as Server-Sent Events."""
    return StreamingResponse(
        _sse_stream(chat(db, current_user, data, redis)),
        media_type="text/event-stream",
    )


# ---- Word collection endpoints ---------------------------------------------


@router.post(
    "/words",
    response_model=ResponseModel[WordCollectionOut],
    summary="Save a word",
)
async def save_word_endpoint(
    data: WordCollectionCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Save (upsert) a collected word for the current user."""
    word = await save_word(db, current_user.id, data)
    return success(word)


@router.get(
    "/words",
    response_model=ResponseModel[WordListResponse],
    summary="List collected words",
)
async def list_words_endpoint(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    mastery_level: Optional[MasteryLevel] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=255),
) -> dict:
    """List the current user's collected words with pagination.

    Optionally filter by ``mastery_level`` (``new``, ``learning``,
    ``familiar``, ``mastered``) and/or search by word text
    (case-insensitive).
    """
    result = await list_words(
        db, current_user.id, page, page_size, mastery_level, search
    )
    return success(result)


@router.put(
    "/words/{word_id}",
    response_model=ResponseModel[WordCollectionOut],
    summary="Update word mastery",
)
async def update_word_endpoint(
    word_id: int,
    data: WordCollectionUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Update the mastery level and/or study count of a collected word."""
    word = await update_word_mastery(db, current_user.id, word_id, data)
    return success(word)


@router.delete(
    "/words/{word_id}",
    response_model=ResponseModel[None],
    summary="Delete a word",
)
async def delete_word_endpoint(
    word_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Delete a collected word for the current user."""
    await remove_word(db, current_user.id, word_id)
    return success(None)


# ---- Sentence collection endpoints -----------------------------------------


@router.post(
    "/sentences",
    response_model=ResponseModel[SentenceCollectionOut],
    status_code=201,
    summary="Save a sentence",
)
async def save_sentence_endpoint(
    data: SentenceCollectionCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Save a collected sentence for the current user."""
    sentence = await save_sentence(db, current_user.id, data)
    return success(sentence)


@router.get(
    "/sentences",
    response_model=ResponseModel[SentenceListResponse],
    summary="List collected sentences",
)
async def list_sentences_endpoint(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None, max_length=255),
) -> dict:
    """List the current user's collected sentences with pagination.

    Optionally search by sentence text (case-insensitive).
    """
    result = await list_sentences(
        db, current_user.id, page, page_size, search
    )
    return success(result)


@router.put(
    "/sentences/{sentence_id}",
    response_model=ResponseModel[SentenceCollectionOut],
    summary="Update sentence note",
)
async def update_sentence_endpoint(
    sentence_id: int,
    data: SentenceCollectionUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Update the note on a collected sentence for the current user."""
    sentence = await update_sentence_note(
        db, current_user.id, sentence_id, data
    )
    return success(sentence)


@router.delete(
    "/sentences/{sentence_id}",
    response_model=ResponseModel[None],
    summary="Delete a sentence",
)
async def delete_sentence_endpoint(
    sentence_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Delete a collected sentence for the current user."""
    await remove_sentence(db, current_user.id, sentence_id)
    return success(None)


# ---- Reading history endpoints ---------------------------------------------


@router.post(
    "/history",
    response_model=ResponseModel[ReadingHistoryOut],
    status_code=201,
    summary="Start reading",
)
async def start_reading_endpoint(
    data: ReadingHistoryCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Start a new reading session for an article."""
    history = await start_reading(db, current_user.id, data)
    return success(history)


@router.put(
    "/history/{history_id}",
    response_model=ResponseModel[ReadingHistoryOut],
    summary="End reading",
)
async def end_reading_endpoint(
    history_id: int,
    data: ReadingHistoryUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """End a reading session, recording end time and duration."""
    history = await end_reading(db, current_user.id, history_id, data)
    return success(history)


@router.get(
    "/history",
    response_model=ResponseModel[ReadingHistoryWithArticleListResponse],
    summary="List reading history",
)
async def list_history_endpoint(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    """List the current user's reading history with pagination."""
    result = await list_histories(db, current_user.id, page, page_size)
    return success(result)


# ---- AI conversation endpoints ---------------------------------------------


@router.get(
    "/conversations/{article_id}",
    response_model=ResponseModel[ConversationListResponse],
    summary="List chat history for an article",
)
async def list_conversations_endpoint(
    article_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """List the current user's AI chat history for a specific article.

    Returns up to 50 most recent messages in chronological order so the
    frontend can restore a chat session after a page refresh.
    """
    result = await list_conversations(db, current_user.id, article_id)
    return success(result)
