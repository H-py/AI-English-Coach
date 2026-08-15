"""安全工具：密码哈希与 JWT 助手。

密码哈希使用 passlib 的 bcrypt 方案。JWT 助手负责创建和验证用于认证的
令牌。二者共同构成了 auth/users 模块所依赖的稳定安全接口。
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.exceptions import BizException, CODE_AUTH_ERROR

# ---- 密码哈希 ----
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = settings.JWT_ALGORITHM
SECRET_KEY = settings.JWT_SECRET_KEY


def hash_password(password: str) -> str:
    """使用 bcrypt 对明文密码进行哈希。"""
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与 bcrypt 哈希是否匹配。"""
    return _pwd_context.verify(plain_password, hashed_password)


def _create_token(
    subject: str | int,
    expires_delta: timedelta,
    token_type: str,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    """为 ``subject`` 构建并编码 JWT。

    Args:
        subject: 主体标识（通常是用户 id）。
        expires_delta: 令牌的有效时长。
        token_type: ``"access"`` 或 ``"refresh"``（存入 ``type`` 声明中）。
        extra_claims: 合并到负载中的额外声明。

    Returns:
        编码后的 JWT 字符串。
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
    """创建一个短期访问令牌。"""
    return _create_token(
        subject,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "access",
        extra_claims,
    )


def create_refresh_token(
    subject: str | int, extra_claims: Optional[dict[str, Any]] = None
) -> str:
    """创建一个长期刷新令牌。"""
    return _create_token(
        subject,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "refresh",
        extra_claims,
    )


def verify_token(token: str, expected_type: Optional[str] = None) -> dict[str, Any]:
    """解码并校验 JWT。

    Args:
        token: 编码后的 JWT 字符串。
        expected_type: 若提供，则 ``type`` 声明必须与之匹配（例如
            ``"access"`` 或 ``"refresh"``）。

    Returns:
        解码后的负载字典。

    Raises:
        BizException: 当令牌已过期、格式错误，或类型与预期不符时抛出。
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise BizException(
            "token has expired", code=CODE_AUTH_ERROR, http_status=401
        )
    except jwt.InvalidTokenError:
        raise BizException(
            "invalid token", code=CODE_AUTH_ERROR, http_status=401
        )

    if expected_type is not None and payload.get("type") != expected_type:
        raise BizException(
            f"unexpected token type: expected {expected_type}",
            code=CODE_AUTH_ERROR,
            http_status=401,
        )
    return payload
