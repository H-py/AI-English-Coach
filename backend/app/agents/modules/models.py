"""Agent 模块的 ORM 模型。

定义了支撑 Agent 执行追踪的两张表：

* ``agent_sessions`` — 一次完整的 Agent 执行会话，记录用户消息、
  最终回答、总步数和执行状态。
* ``agent_steps``    — 会话中的每一步推理/工具调用记录，包含思考
  文本、工具名、工具参数和工具返回结果。

所有模型均采用 SQLAlchemy 2.0 的 ``Mapped`` / ``mapped_column`` 风格，
并注册到共享的 :class:`~app.core.database.Base` 上，以便 Alembic
自动生成迁移时能够发现它们。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AgentConversation(Base):
    """Agent 多轮对话。

    一次对话由多条连续的 AgentSession 组成，用户在同一上下文中
    连续提问时复用同一个 conversation。``title`` 默认为 "新对话"，
    可在后续更新。

    ``sessions`` 关系以 ``cascade="all, delete-orphan"`` 级联删除，
    删除对话时会自动删除其下所有会话及步骤记录。
    """

    __tablename__ = "agent_conversations"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, default="新对话"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    sessions: Mapped[list["AgentSession"]] = relationship(
        "AgentSession",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AgentSession.created_at",
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"<AgentConversation id={self.id} "
            f"title={self.title!r}>"
        )


class AgentSession(Base):
    """一次完整的 Agent 执行会话。

    每当用户向 Agent 发送一条消息时，都会创建一条会话记录。会话
    记录了用户输入的原始消息、Agent 最终生成的回答、执行的总步数
    以及执行状态（``completed`` / ``failed`` / ``max_iterations``）。

    ``article_id`` 和 ``history_id`` 将会话关联到具体的文章和阅读
    会话，便于后续查询和统计。
    """

    __tablename__ = "agent_sessions"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True, nullable=False
    )
    article_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("articles.id"), nullable=True, default=None
    )
    history_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("reading_histories.id"),
        nullable=True,
        default=None,
    )
    conversation_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("agent_conversations.id"),
        nullable=True,
        default=None,
    )
    agent_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    final_answer: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None
    )
    total_steps: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="completed",
        server_default="completed",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # 关联的对话（可选），同一对话下的多条会话构成多轮对话上下文。
    conversation: Mapped[Optional["AgentConversation"]] = relationship(
        "AgentConversation", back_populates="sessions"
    )

    # 关联的执行步骤列表，按 step_order 排序。
    # 默认懒加载，在需要时通过 selectinload 显式预加载。
    steps: Mapped[list["AgentStepRecord"]] = relationship(
        "AgentStepRecord",
        order_by="AgentStepRecord.step_order",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"<AgentSession id={self.id} "
            f"agent_type={self.agent_type!r} status={self.status!r}>"
        )


class AgentStepRecord(Base):
    """Agent 执行过程中的单步记录。

    每个会话包含多个步骤记录，按 ``step_order`` 排列。步骤类型包括
    ``thinking``（思考）、``tool_call``（工具调用）和
    ``tool_result``（工具结果）。

    ``tool_name``、``tool_arguments`` 和 ``tool_result`` 仅在工具
    相关步骤中有值，其余步骤为 ``None``。``tool_arguments`` 和
    ``tool_result`` 以 JSON 格式存储，便于后续分析和回放。
    """

    __tablename__ = "agent_steps"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agent_sessions.id"),
        index=True,
        nullable=False,
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    content: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None
    )
    tool_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, default=None
    )
    tool_arguments: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, default=None
    )
    tool_result: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"<AgentStepRecord id={self.id} "
            f"order={self.step_order} type={self.step_type!r}>"
        )
