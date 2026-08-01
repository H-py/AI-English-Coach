"""Async database infrastructure.

Provides the SQLAlchemy async engine, a session maker, the declarative
``Base`` class used by every ORM model, and the ``get_db`` FastAPI dependency
that yields an :class:`AsyncSession`.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Async engine configured with connection pooling tuned for async usage.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_DEBUG,
    pool_pre_ping=True,
    future=True,
)

# Session factory bound to the async engine.
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Declarative base class for all ORM models.

    Every feature module imports :class:`Base` to declare its tables so that
    Alembic can discover them through metadata reflection.
    """

    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides a transactional async session.

    The session is automatically closed when the request completes. If an
    exception occurs the transaction is rolled back.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
