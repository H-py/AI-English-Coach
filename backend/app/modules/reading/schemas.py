"""Pydantic schemas for the reading module.

Describes the wire shapes for AI-interaction requests, word and sentence
collections, and reading history. Written in the Pydantic v2 style with
``model_config`` / ``ConfigDict`` and ``from_attributes`` enabled on the
read schemas so they can be built directly from ORM instances.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.modules.reading.models import MasteryLevel


# ---- AI interaction requests ------------------------------------------------


class ExplainWordRequest(BaseModel):
    """Request to explain a single word within its surrounding context."""

    word: str = Field(min_length=1, max_length=255)
    context: str
    article_id: int


class AnalyzeSentenceRequest(BaseModel):
    """Request to analyze the structure of a single sentence."""

    sentence: str
    article_id: int


class SentenceTranslationRequest(BaseModel):
    """Request to translate a sentence into Chinese."""

    sentence: str
    article_id: int


class ParagraphSummaryRequest(BaseModel):
    """Request to summarize a single paragraph."""

    paragraph: str
    article_id: int


class ChatRequest(BaseModel):
    """Request to send a message to the article-aware AI coach."""

    message: str
    article_id: int


# ---- Word collection schemas ------------------------------------------------


class WordCollectionCreate(BaseModel):
    """Payload for saving (upserting) a collected word.

    ``article_id`` and ``ai_explanation`` are optional because a learner
    may save a word from a source other than an article, or before an AI
    explanation has been generated.
    """

    word: str = Field(min_length=1, max_length=255)
    context: str
    article_id: Optional[int] = None
    ai_explanation: Optional[str] = None


class WordCollectionOut(BaseModel):
    """Full representation of a collected word returned to clients."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    word: str
    context: str
    article_id: Optional[int] = None
    ai_explanation: Optional[str] = None
    mastery_level: MasteryLevel
    study_count: int
    last_studied_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class WordCollectionUpdate(BaseModel):
    """Partial-update payload for a collected word's mastery tracking.

    Both fields are optional so that clients can update either the
    mastery level, the study count, or both at once.
    """

    mastery_level: Optional[MasteryLevel] = None
    study_count: Optional[int] = None


class WordListResponse(BaseModel):
    """Paginated list of collected words with a total count."""

    items: list[WordCollectionOut]
    total: int


# ---- Sentence collection schemas --------------------------------------------


class SentenceCollectionCreate(BaseModel):
    """Payload for saving a collected sentence."""

    sentence: str
    article_id: Optional[int] = None
    note: Optional[str] = None


class SentenceCollectionOut(BaseModel):
    """Full representation of a collected sentence returned to clients."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    sentence: str
    article_id: Optional[int] = None
    note: Optional[str] = None
    created_at: datetime


class SentenceCollectionUpdate(BaseModel):
    """Partial-update payload for a collected sentence's note.

    Only ``note`` is updatable; the sentence text itself is immutable
    once saved.
    """

    note: Optional[str] = None


class SentenceListResponse(BaseModel):
    """Paginated list of collected sentences with a total count."""

    items: list[SentenceCollectionOut]
    total: int


# ---- Reading history schemas ------------------------------------------------


class ReadingHistoryCreate(BaseModel):
    """Payload for starting a new reading session."""

    article_id: int


class ReadingHistoryOut(BaseModel):
    """Full representation of a reading-history entry returned to clients."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    article_id: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    created_at: datetime


class ReadingHistoryUpdate(BaseModel):
    """Partial-update payload for ending a reading session.

    Typically both ``ended_at`` and ``duration_seconds`` are supplied
    together when the learner stops reading, but each is optional so the
    payload remains flexible.
    """

    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None


class ReadingHistoryListResponse(BaseModel):
    """Paginated list of reading-history entries with a total count."""

    items: list[ReadingHistoryOut]
    total: int


class ReadingHistoryWithArticleOut(BaseModel):
    """Reading-history entry enriched with the article title.

    Built from a ``(ReadingHistory, article_title)`` tuple returned by
    :func:`list_histories_with_article` in the repository.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    article_id: int
    article_title: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    created_at: datetime


class ReadingHistoryWithArticleListResponse(BaseModel):
    """Paginated list of reading-history entries with article titles."""

    items: list[ReadingHistoryWithArticleOut]
    total: int
