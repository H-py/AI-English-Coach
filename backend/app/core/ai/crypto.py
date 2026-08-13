"""用户 API Key 的加密存储与掩码工具。

使用 Fernet 对称加密对用户自定义的大模型 API Key 进行静态加密。
当 ``AI_API_KEY_SECRET`` 为空时回退到明文存储（开发便利），此时
``encrypt`` / ``decrypt`` 均原样透传。
"""

import base64
import hashlib
import logging

from app.core.ai.deepseek import USER_AI_CONFIG_ERROR_CODE
from app.core.config import settings
from app.core.exceptions import BizException
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

# 掩码显示：sk-****last4（过短则全部隐藏）。
_MASK_SHORT_LEN = 8


def _get_fernet():
    """根据配置派生 Fernet 实例。

    ``AI_API_KEY_SECRET`` 优先；未设置时回退到 ``JWT_SECRET_KEY``，保证
    默认启用静态加密。两者均未设置时才返回 ``None``（明文模式，仅开发）。
    """
    secret = settings.AI_API_KEY_SECRET or settings.JWT_SECRET_KEY
    if not secret:
        return None
    key = base64.urlsafe_b64encode(
        hashlib.sha256(secret.encode("utf-8")).digest()
    )
    return Fernet(key)


def encrypt_api_key(plain: str) -> str:
    """加密明文 API Key；未配置 secret 时返回原文。"""
    if not plain:
        return plain
    fernet = _get_fernet()
    if fernet is None:
        logger.warning(
            "AI_API_KEY_SECRET is not set; storing API key in plaintext"
        )
        return plain
    return fernet.encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_api_key(stored: str) -> str:
    """解密存储的 API Key；未配置 secret 时按明文透传。

    兼容历史明文数据：值若不像 Fernet 令牌则视为明文原样返回（该行数据
    在下次保存时会重新加密）。
    """
    if not stored:
        return stored
    fernet = _get_fernet()
    if fernet is None:
        return stored
    if not stored.startswith("gAAAA"):
        return stored
    try:
        return fernet.decrypt(stored.encode("utf-8")).decode("utf-8")
    except Exception:
        raise BizException(
            "存储的 API Key 无法解密，AI_API_KEY_SECRET 可能已变更，请重新保存模型配置",
            code=USER_AI_CONFIG_ERROR_CODE,
        )


def mask_api_key(plain: str) -> str:
    """将明文 API Key 转换为掩码形式用于展示。"""
    if not plain:
        return ""
    if len(plain) <= _MASK_SHORT_LEN:
        return "****"
    return f"{plain[:2]}****{plain[-4:]}"
