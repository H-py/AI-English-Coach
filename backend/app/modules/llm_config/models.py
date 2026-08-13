"""用户自定义大模型配置的 ORM 模型。

定义 ``user_llm_configs`` 表：每个用户可配置多条 OpenAI 兼容模型服务
（显示名称、Base URL、模型名与 API Key，API Key 静态加密存储）。同一
用户至多一条 ``is_active=True`` 的记录（通过部分唯一索引保证），即
"当前使用中的模型"；没有激活记录时调用回落到默认模型。

API Key 通过 :mod:`app.core.ai.crypto` 加密，绝不返回明文给前端。

模型采用 SQLAlchemy 2.0 的 ``Mapped`` / ``mapped_column`` 风格，并注册
到共享的 :class:`~app.core.database.Base` 上，以便 Alembic 自动生成
迁移时能够发现它。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserLlmConfig(Base):
    """单个用户的一条自定义大模型配置。

    每个用户可有多条；``is_active`` 标记当前使用中的那一条。部分唯一索引
    ``uq_user_llm_configs_one_active`` 保证每个用户至多一条激活记录。
    """

    __tablename__ = "user_llm_configs"
    __table_args__ = (
        # 每用户至多一条激活配置：同一 user_id 下 is_active 为 true 的行唯一。
        Index(
            "uq_user_llm_configs_one_active",
            "user_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )
    provider_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="", server_default=""
    )
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    api_key: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", server_default=""
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
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
        return f"<UserLlmConfig id={self.id} user_id={self.user_id} model={self.model!r}>"
