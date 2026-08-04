"""Reading module ORM models and the mastery-level enumeration.

Defines six tables that together support AI-assisted reading:

* ``word_collections``     — words a learner has saved while reading.
* ``sentence_collections`` — sentences a learner has saved while reading.
* ``reading_histories``    — per-article reading-session records.
* ``ai_conversations``     — chat messages exchanged with the AI coach
  about a specific article.
* ``ai_memories``          — compressed long-term summaries extracted
  from older conversation messages.
* ``user_profiles``        — AI-generated learner profiles derived from
  accumulated memories.

All models follow the SQLAlchemy 2.0 ``Mapped`` / ``mapped_column`` style
and are registered on the shared :class:`~app.core.database.Base` so that
Alembic autogenerate can discover them.
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MasteryLevel(enum.Enum):
    """A learner's mastery of a saved word.

    Progresses from ``new`` (just collected) through ``learning`` and
    ``familiar`` up to ``mastered``. The value is advanced manually by the
    learner or automatically by future spaced-repetition logic.
    """

    new = "new"
    learning = "learning"
    familiar = "familiar"
    mastered = "mastered"


class WordCollection(Base):
    """A word saved by a learner, with context and AI explanation.

    Each (user, word) pair is unique: saving the same word again updates
    the stored context and explanation rather than creating a duplicate.
    The ``mastery_level`` and ``study_count`` track the learner's progress
    with the word.
    """

    __tablename__ = "word_collections"
    __table_args__ = (
        UniqueConstraint("user_id", "word", name="uq_word_collections_user_word"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True, nullable=False
    )
    word: Mapped[str] = mapped_column(String(255), nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False)
    article_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("articles.id"), nullable=True, default=None
    )
    ai_explanation: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None
    )
    mastery_level: Mapped[MasteryLevel] = mapped_column(
        Enum(MasteryLevel),
        nullable=False,
        default=MasteryLevel.new,
        server_default="new",
    )
    study_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_studied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<WordCollection id={self.id} word={self.word!r}>"


class SentenceCollection(Base):
    """A sentence saved by a learner, optionally with a personal note."""

    __tablename__ = "sentence_collections"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True, nullable=False
    )
    sentence: Mapped[str] = mapped_column(Text, nullable=False)
    article_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("articles.id"), nullable=True, default=None
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<SentenceCollection id={self.id}>"


class ReadingHistory(Base):
    """A reading session record for an article (one row per user+article).

    Each (user, article) pair has at most one row. ``read_count`` tracks
    how many times the user has opened the article; ``started_at`` /
    ``ended_at`` / ``duration_seconds`` always reflect the **latest**
    reading session.
    """

    __tablename__ = "reading_histories"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "article_id", name="uq_reading_histories_user_article"
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True, nullable=False
    )
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("articles.id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    duration_seconds: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=None
    )
    read_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ReadingHistory id={self.id} article_id={self.article_id}>"


class AiConversation(Base):
    """A single chat message exchanged with the AI coach about an article.

    Both ``user`` and ``assistant`` messages are persisted so that
    conversation history can be loaded as context for subsequent turns.
    The ``is_summarized`` flag indicates whether this message has been
    compressed into an :class:`AiMemory` — summarized messages are
    excluded from short-term context loading but retained for history
    display.
    """

    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True, nullable=False
    )
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("articles.id"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_summarized: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AiConversation id={self.id} role={self.role!r}>"


class AiMemory(Base):
    """A compressed long-term memory extracted from conversation history.

    When unsummarized messages exceed the token threshold, the oldest
    batch is sent to the LLM for summarization. The resulting summary is
    stored here as a single row. Memories are scoped per user and
    optionally per article (``article_id=None`` means global).

    The ``memory_type`` distinguishes summaries (``summary``), factual
    notes (``fact``), recurring mistakes (``mistake``), and learner
    preferences (``preference``). The ``importance`` score (0.0-1.0)
    guides which memories are loaded first when the token budget is
    tight.
    """

    __tablename__ = "ai_memories"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True, nullable=False
    )
    article_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("articles.id"), nullable=True, default=None
    )
    memory_type: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5, server_default="0.5"
    )
    token_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AiMemory id={self.id} type={self.memory_type!r}>"


class UserProfile(Base):
    """An AI-generated learner profile derived from accumulated memories.

    One row per user. The profile is periodically refreshed (every few
    summarization cycles) by feeding recent memories to the LLM. The
    natural-language ``profile_summary`` is injected into the system
    prompt so all AI endpoints can personalize their responses.

    Structured fields (``strengths``, ``weaknesses``, ``common_mistakes``,
    ``interests``) are JSON arrays for programmatic use; the summary
    text is what the LLM actually reads.
    """

    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), primary_key=True
    )
    profile_summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None
    )
    strengths: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    weaknesses: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    learning_style: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, default=None
    )
    interests: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    common_mistakes: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<UserProfile user_id={self.user_id}>"
