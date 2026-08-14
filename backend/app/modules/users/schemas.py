"""users 模块的 Pydantic 模式（schema）。

这些模式描述了用户画像端点使用的传输数据结构：共享的基础字段、
完整的读取表示（``UserOut``）以及部分更新载荷（``UserUpdate``）。
采用 Pydantic v2 风格，使用 ``model_config`` / ``ConfigDict``。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.users.models import EnglishLevel, UserRole


class UserBase(BaseModel):
    """请求与响应模式共用的用户字段。"""

    email: EmailStr
    username: str = Field(min_length=2, max_length=50)


class UserOut(UserBase):
    """返回给客户端的完整用户表示。

    包含持久化的标识符和元数据。启用 ``from_attributes``，以便通过
    :meth:`UserOut.model_validate` 直接从 ORM ``User`` 实例构建。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    avatar_url: Optional[str] = None
    english_level: EnglishLevel
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None


class UserUpdate(BaseModel):
    """当前用户画像的部分更新载荷。

    所有字段都是可选的，以便客户端只提交希望修改的字段。服务层使用
    ``exclude_unset`` 仅应用提供的值。
    """

    username: Optional[str] = Field(default=None, min_length=2, max_length=50)
    avatar_url: Optional[str] = None
    english_level: Optional[EnglishLevel] = None


class PasswordUpdate(BaseModel):
    """修改密码的载荷。

    需提供旧密码用于验证，新密码长度 6-128 位。
    """

    old_password: str
    new_password: str = Field(min_length=6, max_length=128)
