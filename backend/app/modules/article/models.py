"""Article ORM model and difficulty enumeration.

Defines the ``articles`` table and the :class:`Difficulty` enum based on the
CEFR (Common European Framework of Reference) proficiency scale. The model
follows the SQLAlchemy 2.0 ``Mapped`` / ``mapped_column`` style and is
registered on the shared :class:`~app.core.database.Base` so that Alembic
autogenerate can discover it.
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Difficulty(enum.Enum):
    """CEFR (Common European Framework of Reference) proficiency levels.

    Ranges from A1 (beginner) to C2 (mastery). Used to classify article
    difficulty so readers can find content matching their level.
    """

    a1 = "a1"
    a2 = "a2"
    b1 = "b1"
    b2 = "b2"
    c1 = "c1"
    c2 = "c2"


class Article(Base):
    """A reading article available to learners.

    Stores the full article content alongside metadata such as title,
    summary, difficulty level, word count, estimated reading time, cover
    image, tags, and view statistics. The ``tags`` column uses the
    ``JSON`` type to store a list of string tags.
    """

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None
    )
    source: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None
    )
    difficulty: Mapped[Difficulty] = mapped_column(
        Enum(Difficulty),
        nullable=False,
        default=Difficulty.b1,
        server_default="b1",
    )
    word_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    reading_time: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=None
    )
    cover_url: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True, default=None
    )
    tags: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    view_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
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
        return f"<Article id={self.id} title={self.title!r}>"
