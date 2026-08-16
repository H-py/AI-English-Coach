"""共享的 FastAPI 依赖。

重新导出数据库和 redis 依赖，使路由模块有一个统一、熟知的导入路径来获取
公共资源。同时还定义了 ``get_current_user`` 依赖，用于通过 Bearer 访问
令牌对请求进行认证。
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

# 通用带注解依赖，便于在各路由模块中简洁复用。
DbSession = Annotated[AsyncSession, Depends(get_db)]
RedisClient = Annotated[aioredis.Redis, Depends(get_redis)]

# 用于从 ``Authorization`` 头中提取访问令牌的 Bearer 令牌方案。
# ``auto_error=False`` 使我们能够抛出自定义的 ``BizException``（状态码 401），
# 而不是 FastAPI 默认的 403。
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    db: DbSession,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> User:
    """校验 Bearer 访问令牌并返回当前用户。

    Args:
        db: 当前的异步会话（通过 :data:`DbSession` 注入）。
        credentials: 从 ``Authorization`` 头中提取的 Bearer 凭证；若不存在则为
            ``None``。

    Returns:
        已认证的 :class:`User`。

    Raises:
        BizException: 若无凭证、令牌无效、用户已不存在或账号被禁用。所有
            情况均使用 ``http_status=401``。
    """
    if credentials is None:
        raise BizException("未登录或登录已过期", code=CODE_AUTH_ERROR, http_status=401)
    payload = verify_token(credentials.credentials, expected_type="access")
    user_id = int(payload["sub"])
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise BizException("用户不存在", code=CODE_AUTH_ERROR, http_status=401)
    if not user.is_active:
        raise BizException("账号已被禁用", code=CODE_AUTH_ERROR, http_status=401)
    return user


# 用于将当前用户简洁注入路由的带注解别名。
CurrentUser = Annotated[User, Depends(get_current_user)]

# 禁止访问错误码（2xxxx —— 授权）。
CODE_FORBIDDEN = 20005


async def get_admin_user(current_user: CurrentUser) -> User:
    """确保当前用户具有 ``admin`` 角色。

    Args:
        current_user: 已认证的用户（通过 :data:`CurrentUser` 注入）。

    Returns:
        若该用户是管理员，则返回同一用户实例。

    Raises:
        BizException: 若用户不是管理员（code ``20005``，``http_status=403``）。
    """
    if current_user.role != UserRole.admin:
        raise BizException(
            "需要管理员权限",
            code=CODE_FORBIDDEN,
            http_status=403,
        )
    return current_user


# 用于将管理员用户简洁注入路由的带注解别名。
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
