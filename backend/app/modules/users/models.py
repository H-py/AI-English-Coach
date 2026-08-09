"""用户 ORM 模型与英语水平枚举。

定义了 ``users`` 表以及 :class:`EnglishLevel` 枚举，后者用于跟踪学习者
自评的英语水平。模型采用 SQLAlchemy 2.0 的 ``Mapped`` /
``mapped_column`` 风格，并注册到共享的
:class:`~app.core.database.Base` 上，以便 Alembic 自动生成迁移时能够
发现它。
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EnglishLevel(enum.Enum):
    """学习者自评的英语水平等级。"""

    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class UserRole(enum.Enum):
    """用于鉴权的用户角色：普通用户或管理员。"""

    user = "user"
    admin = "admin"


class User(Base):
    """应用用户账号。

    存储认证凭据（``password_hash``）以及诸如显示名、头像、英语水平和
    活动/登录时间戳等画像元数据。密码绝不以明文存储，仅持久化 bcrypt
    哈希值。
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    username: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True, default=None
    )
    english_level: Mapped[EnglishLevel] = mapped_column(
        Enum(EnglishLevel),
        nullable=False,
        default=EnglishLevel.beginner,
        server_default="beginner",
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole),
        nullable=False,
        default=UserRole.user,
        server_default="user",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<User id={self.id} email={self.email!r}>"
