"""users 模块的业务逻辑层。

该服务层位于 HTTP 路由与仓库层之间，负责领域规则：将"未找到"翻译为
:class:`BizException`、用户名的唯一性校验、修改密码时验证旧密码，以及
头像上传（类型/大小校验 + 上传到 MinIO）。
"""

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException, CODE_VALIDATION_ERROR
from app.core.security import hash_password, verify_password
from app.core.storage import upload_avatar as upload_avatar_file
from app.modules.users.repository import (
    get_user_by_id,
    get_user_by_username,
    update_user,
)
from app.modules.users.schemas import PasswordUpdate, UserOut, UserUpdate

# 业务错误码：请求的资源不存在。
USER_NOT_FOUND_CODE = 90001
# 用户名已被占用（与 auth 模块注册时的错误码保持一致）。
USERNAME_ALREADY_TAKEN_CODE = 20002
# 修改密码时提供的旧密码错误。
WRONG_OLD_PASSWORD_CODE = 20008

# 头像上传限制：允许的 MIME 类型 -> 扩展名，以及最大字节数。
_ALLOWED_AVATAR_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
_MAX_AVATAR_SIZE = 50 * 1024 * 1024  # 50MB


async def get_user_profile(db: AsyncSession, user_id: int) -> UserOut:
    """返回指定 id 用户的公开画像。

    Args:
        db: 当前活跃的异步会话。
        user_id: 用户的主键。

    Returns:
        由持久化用户构建的 :class:`UserOut`。

    Raises:
        BizException: 若不存在指定 id 的用户（错误码 ``90001``）。
    """
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise BizException("用户不存在", code=USER_NOT_FOUND_CODE)
    return UserOut.model_validate(user)


async def update_profile(
    db: AsyncSession, user_id: int, data: UserUpdate
) -> UserOut:
    """对指定用户应用部分画像更新。

    仅应用 ``data`` 中显式提供的字段（通过 ``exclude_unset``）；
    未提供的字段保持不变。修改用户名时会校验其唯一性。

    Args:
        db: 当前活跃的异步会话。
        user_id: 用户的主键。
        data: 部分更新载荷。

    Returns:
        反映更新后用户的 :class:`UserOut`。

    Raises:
        BizException: 若不存在指定 id 的用户（错误码 ``90001``）或
            用户名已被占用（错误码 ``20002``）。
    """
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise BizException("用户不存在", code=USER_NOT_FOUND_CODE)

    update_data = data.model_dump(exclude_unset=True)

    # 用户名唯一性校验：仅在用户名发生变化时检查。
    new_username = update_data.get("username")
    if new_username is not None and new_username != user.username:
        existing = await get_user_by_username(db, new_username)
        if existing is not None:
            raise BizException(
                "该用户名已被占用", code=USERNAME_ALREADY_TAKEN_CODE
            )

    if update_data:
        user = await update_user(db, user, update_data)
    return UserOut.model_validate(user)


async def update_password(
    db: AsyncSession, user_id: int, data: PasswordUpdate
) -> None:
    """修改用户密码。

    先验证旧密码是否正确，通过后将其替换为新密码的 bcrypt 哈希。

    Args:
        db: 当前活跃的异步会话。
        user_id: 用户的主键。
        data: 修改密码载荷（旧密码 + 新密码）。

    Raises:
        BizException: 若用户不存在（错误码 ``90001``）或旧密码错误
            （错误码 ``20008``）。
    """
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise BizException("用户不存在", code=USER_NOT_FOUND_CODE)

    if not verify_password(data.old_password, user.password_hash):
        raise BizException("原密码错误", code=WRONG_OLD_PASSWORD_CODE)

    await update_user(
        db, user, {"password_hash": hash_password(data.new_password)}
    )


async def upload_avatar(
    db: AsyncSession, user_id: int, file: UploadFile
) -> UserOut:
    """上传并更新用户头像。

    校验图片 MIME 类型与大小，上传到 MinIO，并将生成的头像 URL 写入
    用户记录。

    Args:
        db: 当前活跃的异步会话。
        user_id: 用户的主键。
        file: 前端上传的图片文件。

    Returns:
        更新头像后的 :class:`UserOut`。

    Raises:
        BizException: 若用户不存在（错误码 ``90001``）、文件类型不支持
            或文件过大（错误码 ``10000``）。
    """
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise BizException("用户不存在", code=USER_NOT_FOUND_CODE)

    ext = _ALLOWED_AVATAR_TYPES.get(file.content_type)
    if ext is None:
        raise BizException(
            "不支持的图片格式，仅支持 JPG / PNG / WebP / GIF",
            code=CODE_VALIDATION_ERROR,
        )

    content = await file.read()
    if len(content) > _MAX_AVATAR_SIZE:
        raise BizException(
            "图片大小不能超过 50MB", code=CODE_VALIDATION_ERROR
        )

    avatar_url = upload_avatar_file(user_id, content, file.content_type, ext)
    user = await update_user(db, user, {"avatar_url": avatar_url})
    return UserOut.model_validate(user)
