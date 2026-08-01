"""User ORM model and English-level enumeration.

Defines the ``users`` table and the :class:`EnglishLevel` enum used to track a
learner's self-assessed proficiency. The model follows the SQLAlchemy 2.0
``Mapped`` / ``mapped_column`` style and is registered on the shared
:class:`~app.core.database.Base` so that Alembic autogenerate can discover it.
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EnglishLevel(enum.Enum):
    """Self-assessed English proficiency levels for a learner."""

    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class User(Base):
    """Application user account.

    Stores authentication credentials (``password_hash``) alongside profile
    metadata such as display name, avatar, English level, and activity /
    login timestamps. Passwords are never stored in plain text; only the
    bcrypt hash is persisted.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    username: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True, default=None
    )
    english_level: Mapped[EnglishLevel] = mapped_column(
        Enum(EnglishLevel),
        nullable=False,
        default=EnglishLevel.beginner,
        server_default="beginner",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
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
        return f"<User id={self.id} email={self.email!r}>"
