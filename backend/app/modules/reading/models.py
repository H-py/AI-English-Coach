"""Reading module ORM models and the mastery-level enumeration.

Defines four tables that together support AI-assisted reading:

* ``word_collections``     — words a learner has saved while reading.
* ``sentence_collections`` — sentences a learner has saved while reading.
* ``reading_histories``    — per-article reading-session records.
* ``ai_conversations``     — chat messages exchanged with the AI coach
  about a specific article.

All models follow the SQLAlchemy 2.0 ``Mapped`` / ``mapped_column`` style
and are registered on the shared :class:`~app.core.database.Base` so that
Alembic autogenerate can discover them.
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
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
    """A single reading session for an article.

    ``started_at`` is set when the session begins; ``ended_at`` and
    ``duration_seconds`` are filled in when the learner stops reading.
    """

    __tablename__ = "reading_histories"

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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ReadingHistory id={self.id} article_id={self.article_id}>"


class AiConversation(Base):
    """A single chat message exchanged with the AI coach about an article.

    Both ``user`` and ``assistant`` messages are persisted so that
    conversation history can be loaded as context for subsequent turns.
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AiConversation id={self.id} role={self.role!r}>"
