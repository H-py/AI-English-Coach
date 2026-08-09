"""users 模块的业务逻辑层。

该服务层位于 HTTP 路由与仓库层之间，负责领域规则：将"未找到"翻译为
:class:`BizException`，并决定更新载荷中哪些字段会被实际应用。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.modules.users.repository import get_user_by_id, update_user
from app.modules.users.schemas import UserOut, UserUpdate

# 业务错误码：请求的资源不存在。
USER_NOT_FOUND_CODE = 90001


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
        raise BizException("user not found", code=USER_NOT_FOUND_CODE)
    return UserOut.model_validate(user)


async def update_profile(
    db: AsyncSession, user_id: int, data: UserUpdate
) -> UserOut:
    """对指定用户应用部分画像更新。

    仅应用 ``data`` 中显式提供的字段（通过 ``exclude_unset``）；
    未提供的字段保持不变。

    Args:
        db: 当前活跃的异步会话。
        user_id: 用户的主键。
        data: 部分更新载荷。

    Returns:
        反映更新后用户的 :class:`UserOut`。

    Raises:
        BizException: 若不存在指定 id 的用户（错误码 ``90001``）。
    """
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise BizException("user not found", code=USER_NOT_FOUND_CODE)

    update_data = data.model_dump(exclude_unset=True)
    if update_data:
        user = await update_user(db, user, update_data)
    return UserOut.model_validate(user)
