"""Security utilities: password hashing and JWT helpers.

Password hashing uses passlib with the bcrypt scheme. JWT helpers create and
verify tokens for authentication. Together they form the stable security
interface that the auth/users modules build on.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.exceptions import BizException, CODE_AUTH_ERROR

# ---- Password hashing ----
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = settings.JWT_ALGORITHM
SECRET_KEY = settings.JWT_SECRET_KEY


def hash_password(password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return _pwd_context.verify(plain_password, hashed_password)


def _create_token(
    subject: str | int,
    expires_delta: timedelta,
    token_type: str,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    """Build and encode a JWT for ``subject``.

    Args:
        subject: The principal identifier (typically a user id).
        expires_delta: How long the token remains valid.
        token_type: ``"access"`` or ``"refresh"`` (stored in the ``type`` claim).
        extra_claims: Additional claims merged into the payload.

    Returns:
        The encoded JWT string.
    """
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(
    subject: str | int, extra_claims: Optional[dict[str, Any]] = None
) -> str:
    """Create a short-lived access token."""
    return _create_token(
        subject,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "access",
        extra_claims,
    )


def create_refresh_token(
    subject: str | int, extra_claims: Optional[dict[str, Any]] = None
) -> str:
    """Create a long-lived refresh token."""
    return _create_token(
        subject,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "refresh",
        extra_claims,
    )


def verify_token(token: str, expected_type: Optional[str] = None) -> dict[str, Any]:
    """Decode and validate a JWT.

    Args:
        token: The encoded JWT string.
        expected_type: If provided, the ``type`` claim must match (e.g.
            ``"access"`` or ``"refresh"``).

    Returns:
        The decoded payload as a dict.

    Raises:
        BizException: If the token is expired, malformed, or the type does not
            match expectations.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise BizException("token has expired", code=CODE_AUTH_ERROR)
    except jwt.InvalidTokenError:
        raise BizException("invalid token", code=CODE_AUTH_ERROR)

    if expected_type is not None and payload.get("type") != expected_type:
        raise BizException(
            f"unexpected token type: expected {expected_type}", code=CODE_AUTH_ERROR
        )
    return payload
