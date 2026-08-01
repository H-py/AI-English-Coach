"""HTTP routes for the current user's own profile.

All endpoints are scoped to the authenticated user (``/users/me``) and rely
on the :func:`get_current_user` dependency to resolve the caller from the
Bearer access token.
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.response import ResponseModel, success
from app.modules.users.schemas import UserOut, UserUpdate
from app.modules.users.service import get_user_profile, update_profile

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=ResponseModel[UserOut])
async def get_my_profile(current_user: CurrentUser) -> dict:
    """Return the profile of the currently authenticated user."""
    return success(UserOut.model_validate(current_user))


@router.put("/me", response_model=ResponseModel[UserOut])
async def update_my_profile(
    data: UserUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Update the profile of the currently authenticated user."""
    updated = await update_profile(db, current_user.id, data)
    return success(updated)
