"""Database access layer for the users module.

All functions are async and operate on the shared :class:`AsyncSession`.
They perform the persistence mechanics (``add`` / ``flush`` / ``refresh``)
while leaving transaction commit/rollback to the ``get_db`` dependency,
which wraps each request in a single transaction.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    """Fetch a single user by its primary key.

    Args:
        db: The active async session.
        user_id: The user's primary key.

    Returns:
        The :class:`User` instance, or ``None`` if no user matches.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalars().first()


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Fetch a single user by its email address.

    Args:
        db: The active async session.
        email: The exact email to look up.

    Returns:
        The :class:`User` instance, or ``None`` if no user matches.
    """
    result = await db.execute(select(User).where(User.email == email))
    return result.scalars().first()


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    """Fetch a single user by its username.

    Args:
        db: The active async session.
        username: The exact username to look up.

    Returns:
        The :class:`User` instance, or ``None`` if no user matches.
    """
    result = await db.execute(select(User).where(User.username == username))
    return result.scalars().first()


async def create_user(
    db: AsyncSession, email: str, username: str, password_hash: str
) -> User:
    """Create and persist a new user.

    The user is flushed (not committed) so that server-side defaults such as
    ``id`` and ``created_at`` are populated and available on the returned
    instance, while the outer request transaction retains commit control.

    Args:
        db: The active async session.
        email: The user's email address.
        username: The user's display name.
        password_hash: The pre-hashed password (never plain text).

    Returns:
        The newly created :class:`User` with refreshed attributes.
    """
    user = User(email=email, username=username, password_hash=password_hash)
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def update_user(db: AsyncSession, user: User, data: dict) -> User:
    """Apply a set of field updates to an existing user.

    Only the keys present in ``data`` are written. The changes are flushed so
    that ``onupdate`` defaults (e.g. ``updated_at``) take effect, and the
    instance is refreshed before being returned.

    Args:
        db: The active async session.
        user: The :class:`User` instance to update.
        data: A mapping of attribute name to new value.

    Returns:
        The updated :class:`User` with refreshed attributes.
    """
    for key, value in data.items():
        setattr(user, key, value)
    await db.flush()
    await db.refresh(user)
    return user


async def update_last_login(db: AsyncSession, user: User) -> User:
    """Stamp the user's ``last_login_at`` to the current UTC time.

    Args:
        db: The active async session.
        user: The :class:`User` instance that just authenticated.

    Returns:
        The updated :class:`User` with refreshed attributes.
    """
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(user)
    return user
