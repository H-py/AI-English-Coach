"""当前用户自身画像的 HTTP 路由。

所有端点都限定在已认证用户范围内（``/users/me``），并依赖
:func:`get_current_user` 依赖从 Bearer 访问令牌中解析出调用者。
"""

from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from app.api.deps import CurrentUser, DbSession
from app.core.response import ResponseModel, success
from app.modules.users.schemas import PasswordUpdate, UserOut, UserUpdate
from app.modules.users.service import (
    get_user_profile,
    update_password,
    update_profile,
    upload_avatar,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=ResponseModel[UserOut])
async def get_my_profile(current_user: CurrentUser) -> dict:
    """返回当前已认证用户的画像。"""
    return success(UserOut.model_validate(current_user))


@router.put("/me", response_model=ResponseModel[UserOut])
async def update_my_profile(
    data: UserUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """更新当前已认证用户的画像（用户名 / 头像 / 英语水平）。"""
    updated = await update_profile(db, current_user.id, data)
    return success(updated)


@router.post("/me/password", response_model=ResponseModel[None])
async def update_my_password(
    data: PasswordUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """修改当前已认证用户的密码（需验证旧密码）。"""
    await update_password(db, current_user.id, data)
    return success(None)


@router.post("/me/avatar", response_model=ResponseModel[UserOut])
async def upload_my_avatar(
    file: Annotated[UploadFile, File(...)],
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """上传并更新当前已认证用户的头像。"""
    updated = await upload_avatar(db, current_user.id, file)
    return success(updated)
