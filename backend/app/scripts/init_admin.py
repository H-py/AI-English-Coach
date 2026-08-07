"""Standalone script to create or upgrade the initial admin account.

Usage::

    cd backend
    python -m app.scripts.init_admin

The admin credentials are read from application settings (``ADMIN_EMAIL``,
``ADMIN_USERNAME``, ``ADMIN_PASSWORD``), which in turn are loaded from
environment variables or the ``.env`` file.

Behaviour:
    * If no user exists with the configured admin email, a new admin user
      is created.
    * If a user with that email already exists but is not an admin, the
      role is upgraded to ``admin``.
    * If the admin user already exists with the correct role, no changes
      are made.
"""

import asyncio

from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.modules.users.models import User, UserRole

logger = get_logger(__name__)


async def init_admin() -> None:
    """Create or upgrade the initial admin user."""
    configure_logging()

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.email == settings.ADMIN_EMAIL)
        )
        user = result.scalars().first()

        if user is None:
            # Create a new admin user.
            user = User(
                email=settings.ADMIN_EMAIL,
                username=settings.ADMIN_USERNAME,
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                role=UserRole.admin,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(
                "Admin user created: id=%s email=%s username=%s",
                user.id,
                user.email,
                user.username,
            )
        elif user.role != UserRole.admin:
            # Upgrade existing user to admin.
            user.role = UserRole.admin
            await session.commit()
            await session.refresh(user)
            logger.info(
                "Existing user upgraded to admin: id=%s email=%s",
                user.id,
                user.email,
            )
        else:
            logger.info(
                "Admin user already exists: id=%s email=%s",
                user.id,
                user.email,
            )

    print(
        f"\nAdmin account ready:\n"
        f"  Email:    {settings.ADMIN_EMAIL}\n"
        f"  Username: {settings.ADMIN_USERNAME}\n"
        f"  Role:     admin\n"
    )


if __name__ == "__main__":
    asyncio.run(init_admin())
