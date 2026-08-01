"""Business-logic layer for the users module.

The service sits between the HTTP routes and the repository. It owns the
domain rules: translating "not found" into a :class:`BizException` and
deciding which fields from an update payload are actually applied.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.modules.users.repository import get_user_by_id, update_user
from app.modules.users.schemas import UserOut, UserUpdate

# Business error code: the requested resource does not exist.
USER_NOT_FOUND_CODE = 90001


async def get_user_profile(db: AsyncSession, user_id: int) -> UserOut:
    """Return the public profile of the user with the given id.

    Args:
        db: The active async session.
        user_id: The user's primary key.

    Returns:
        A :class:`UserOut` built from the persisted user.

    Raises:
        BizException: If no user exists with the given id (code ``90001``).
    """
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise BizException("user not found", code=USER_NOT_FOUND_CODE)
    return UserOut.model_validate(user)


async def update_profile(
    db: AsyncSession, user_id: int, data: UserUpdate
) -> UserOut:
    """Apply a partial profile update for the given user.

    Only fields explicitly provided in ``data`` are applied (via
    ``exclude_unset``); omitted fields are left untouched.

    Args:
        db: The active async session.
        user_id: The user's primary key.
        data: The partial update payload.

    Returns:
        A :class:`UserOut` reflecting the updated user.

    Raises:
        BizException: If no user exists with the given id (code ``90001``).
    """
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise BizException("user not found", code=USER_NOT_FOUND_CODE)

    update_data = data.model_dump(exclude_unset=True)
    if update_data:
        user = await update_user(db, user, update_data)
    return UserOut.model_validate(user)
