"""AI 模块的 ORM 模型。

定义了支撑 AI 辅助学习的三张表：

* ``ai_conversations`` — 针对某篇文章与 AI 教练之间的聊天消息。
* ``ai_memories``      — 从较早的对话消息中提取并压缩的长期记忆摘要。
* ``user_profiles``    — 由累积记忆推导出的、AI 生成的学习者画像。

所有模型均采用 SQLAlchemy 2.0 的 ``Mapped`` / ``mapped_column`` 风格，
并注册到共享的 :class:`~app.core.database.Base` 上，以便 Alembic
自动生成迁移时能够发现它们。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AiConversation(Base):
    """围绕某篇文章与 AI 教练之间交换的单条聊天消息。

    ``user`` 与 ``assistant`` 消息都会被持久化，以便后续轮次可以将
    对话历史加载为上下文。``is_summarized`` 标志表示该消息是否已被
    压缩进 :class:`AiMemory` —— 已摘要的消息不会加载到短期上下文中，
    但会保留以供历史展示。
    """

    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True, nullable=False
    )
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("articles.id"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_summarized: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<AiConversation id={self.id} role={self.role!r}>"


class AiMemory(Base):
    """从对话历史中提取并压缩的长期记忆。

    当未摘要消息超出 token 阈值时，最早的一批会被发送给 LLM 进行
    摘要。生成的摘要作为单行存储在此表中。记忆按用户范围存储，可选
    按文章范围（``article_id=None`` 表示全局记忆）。

    ``memory_type`` 区分摘要（``summary``）、事实笔记（``fact``）、
    反复出现的错误（``mistake``）以及学习者偏好（``preference``）。
    ``importance`` 评分（0.0-1.0）决定了在 token 预算紧张时优先加载
    哪些记忆。
    """

    __tablename__ = "ai_memories"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True, nullable=False
    )
    article_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("articles.id"), nullable=True, default=None
    )
    memory_type: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5, server_default="0.5"
    )
    token_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<AiMemory id={self.id} type={self.memory_type!r}>"


class UserProfile(Base):
    """由累积记忆推导出的、AI 生成的学习者画像。

    每个用户一行。画像会周期性刷新（每几个摘要周期一次），方式是将
    近期记忆喂给 LLM。自然语言形式的 ``profile_summary`` 会被注入到
    系统提示词中，使所有 AI 端点都能个性化其响应。

    结构化字段（``strengths``、``weaknesses``、``common_mistakes``、
    ``interests``）是 JSON 数组，用于程序化处理；而摘要文本才是
    LLM 实际读取的内容。
    """

    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), primary_key=True
    )
    profile_summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None
    )
    strengths: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    weaknesses: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    learning_style: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, default=None
    )
    interests: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    common_mistakes: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<UserProfile user_id={self.user_id}>"
