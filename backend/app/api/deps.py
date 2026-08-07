"""Shared FastAPI dependencies.

Re-exports the database and redis dependencies so that route modules have a
single, well-known import path for common resources. Also defines the
``get_current_user`` dependency used to authenticate requests via a Bearer
access token.
"""

from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import CODE_AUTH_ERROR, BizException
from app.core.redis import get_redis
from app.core.security import verify_token
from app.modules.users.models import User, UserRole
from app.modules.users.repository import get_user_by_id

# Common annotated dependencies for concise reuse across route modules.
DbSession = Annotated[AsyncSession, Depends(get_db)]
RedisClient = Annotated[aioredis.Redis, Depends(get_redis)]

# Bearer token scheme used to extract the access token from the
# ``Authorization`` header. ``auto_error=False`` lets us raise our own
# ``BizException`` (with a 401 status) instead of FastAPI's default 403.
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    db: DbSession,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> User:
    """Validate the Bearer access token and return the current user.

    Args:
        db: The active async session (injected via :data:`DbSession`).
        credentials: The Bearer credentials extracted from the
            ``Authorization`` header, or ``None`` if absent.

    Returns:
        The authenticated :class:`User`.

    Raises:
        BizException: If no credentials are present, the token is invalid,
            the user no longer exists, or the account is disabled. All
            cases use ``http_status=401``.
    """
    if credentials is None:
        raise BizException("not authenticated", code=CODE_AUTH_ERROR, http_status=401)
    payload = verify_token(credentials.credentials, expected_type="access")
    user_id = int(payload["sub"])
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise BizException("user not found", code=CODE_AUTH_ERROR, http_status=401)
    if not user.is_active:
        raise BizException("account is disabled", code=CODE_AUTH_ERROR, http_status=401)
    return user


# Annotated alias for concise injection of the current user into routes.
CurrentUser = Annotated[User, Depends(get_current_user)]

# Forbidden error code (2xxxx – authorisation).
CODE_FORBIDDEN = 20005


async def get_admin_user(current_user: CurrentUser) -> User:
    """Ensure the current user has the ``admin`` role.

    Args:
        current_user: The authenticated user (injected via
            :data:`CurrentUser`).

    Returns:
        The same user instance if they are an admin.

    Raises:
        BizException: If the user is not an admin (code ``20005``,
            ``http_status=403``).
    """
    if current_user.role != UserRole.admin:
        raise BizException(
            "forbidden: admin role required",
            code=CODE_FORBIDDEN,
            http_status=403,
        )
    return current_user


# Annotated alias for concise injection of an admin user into routes.
AdminUser = Annotated[User, Depends(get_admin_user)]

__all__ = [
    "get_db",
    "get_redis",
    "DbSession",
    "RedisClient",
    "get_current_user",
    "CurrentUser",
    "get_admin_user",
    "AdminUser",
]
