"""auth 模块的业务逻辑层。

封装注册、登录和令牌刷新流程。它协调 users repository 与安全工具
（密码哈希、JWT 创建/校验），并在任何失败时抛出带有约定错误码的
:class:`BizException`。

此处使用的错误码约定：
    * ``2xxxx`` —— 认证 / 授权错误
    * ``9xxxx`` —— 通用业务错误（例如用户不存在）
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    verify_token,
)
from app.modules.auth.schemas import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.modules.users.repository import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    update_last_login,
)
from app.modules.users.schemas import UserOut

# 认证错误码（2xxxx）。
EMAIL_ALREADY_REGISTERED_CODE = 20001
USERNAME_ALREADY_TAKEN_CODE = 20002
INVALID_CREDENTIALS_CODE = 20003
ACCOUNT_DISABLED_CODE = 20004

# 业务错误码（9xxxx）。
USER_NOT_FOUND_CODE = 90001


async def register(db: AsyncSession, data: RegisterRequest) -> LoginResponse:
    """创建新用户账号并立即完成认证。

    在创建记录前对邮箱和用户名进行唯一性校验。成功后签发令牌对，
    并写入 ``last_login_at``。

    Args:
        db: 当前活跃的异步会话。
        data: 注册载荷。

    Returns:
        一个 :class:`LoginResponse`，包含新令牌和新用户。

    Raises:
        BizException: 如果邮箱已被注册（错误码 ``20001``）
            或用户名已被占用（错误码 ``20002``）。
    """
    if await get_user_by_email(db, data.email):
        raise BizException("email already registered", code=EMAIL_ALREADY_REGISTERED_CODE)
    if await get_user_by_username(db, data.username):
        raise BizException("username already taken", code=USERNAME_ALREADY_TAKEN_CODE)

    user = await create_user(
        db, data.email, data.username, hash_password(data.password)
    )
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    await update_last_login(db, user)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserOut.model_validate(user),
    )


async def login(db: AsyncSession, data: LoginRequest) -> LoginResponse:
    """通过邮箱和密码对用户进行认证。

    对于未知邮箱和错误密码都使用同一条通用的“邮箱或密码无效”提示，以避免
    用户枚举。被禁用的账号会单独报错。

    Args:
        db: 当前活跃的异步会话。
        data: 登录载荷。

    Returns:
        一个 :class:`LoginResponse`，包含新令牌和用户。

    Raises:
        BizException: 如果凭据无效（错误码 ``20003``，
            ``http_status=401``）或账号被禁用（错误码 ``20004``，
            ``http_status=401``）。
    """
    user = await get_user_by_email(db, data.email)
    if user is None or not verify_password(data.password, user.password_hash):
        raise BizException(
            "invalid email or password",
            code=INVALID_CREDENTIALS_CODE,
            http_status=401,
        )
    if not user.is_active:
        raise BizException(
            "account is disabled", code=ACCOUNT_DISABLED_CODE, http_status=401
        )

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    await update_last_login(db, user)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserOut.model_validate(user),
    )


async def refresh_token(db: AsyncSession, data: RefreshRequest) -> TokenResponse:
    """根据有效的刷新令牌签发新的访问令牌。

    会校验刷新令牌（类型必须为 ``"refresh"``）；无效或过期的令牌会由
    :func:`verify_token` 抛出 :class:`BizException`。刷新令牌本身原样返回，
    以便客户端可以继续使用它直到过期。

    Args:
        db: 当前活跃的异步会话。
        data: 刷新载荷。

    Returns:
        一个 :class:`TokenResponse`，包含新的访问令牌。

    Raises:
        BizException: 如果刷新令牌无效/过期（由 ``verify_token`` 透传）
            或所属用户已不存在（错误码 ``90001``，``http_status=401``）。
    """
    payload = verify_token(data.refresh_token, expected_type="refresh")
    user_id = int(payload["sub"])
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise BizException(
            "user not found", code=USER_NOT_FOUND_CODE, http_status=401
        )

    access_token = create_access_token(user.id)
    return TokenResponse(
        access_token=access_token, refresh_token=data.refresh_token
    )
