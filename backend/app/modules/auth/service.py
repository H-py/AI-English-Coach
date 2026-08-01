"""Business-logic layer for the auth module.

Encapsulates the registration, login, and token-refresh workflows. It
coordinates the users repository with the security helpers (password
hashing and JWT creation/verification) and raises :class:`BizException`
with the agreed-upon error codes for any failure.

Error code conventions used here:
    * ``2xxxx`` -- authentication / authorisation errors
    * ``9xxxx`` -- generic business errors (e.g. user not found)
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

# Auth error codes (2xxxx).
EMAIL_ALREADY_REGISTERED_CODE = 20001
USERNAME_ALREADY_TAKEN_CODE = 20002
INVALID_CREDENTIALS_CODE = 20003
ACCOUNT_DISABLED_CODE = 20004

# Business error code (9xxxx).
USER_NOT_FOUND_CODE = 90001


async def register(db: AsyncSession, data: RegisterRequest) -> LoginResponse:
    """Create a new user account and immediately authenticate it.

    Performs uniqueness checks on email and username before creating the
    record. On success a token pair is issued and ``last_login_at`` is
    stamped.

    Args:
        db: The active async session.
        data: The registration payload.

    Returns:
        A :class:`LoginResponse` with fresh tokens and the new user.

    Raises:
        BizException: If the email is already registered (code ``20001``)
            or the username is already taken (code ``20002``).
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
    """Authenticate a user by email and password.

    Uses a single, generic "invalid email or password" message for both an
    unknown email and a wrong password to avoid user enumeration. A disabled
    account is reported separately.

    Args:
        db: The active async session.
        data: The login payload.

    Returns:
        A :class:`LoginResponse` with fresh tokens and the user.

    Raises:
        BizException: If credentials are invalid (code ``20003``,
            ``http_status=401``) or the account is disabled (code ``20004``,
            ``http_status=401``).
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
    """Issue a new access token from a valid refresh token.

    The refresh token is verified (type must be ``"refresh"``); an invalid
    or expired token surfaces as a :class:`BizException` from
    :func:`verify_token`. The refresh token itself is returned unchanged so
    that clients can keep using it until it expires.

    Args:
        db: The active async session.
        data: The refresh payload.

    Returns:
        A :class:`TokenResponse` with a new access token.

    Raises:
        BizException: If the refresh token is invalid/expired (propagated
            from ``verify_token``) or the owning user no longer exists
            (code ``90001``, ``http_status=401``).
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
