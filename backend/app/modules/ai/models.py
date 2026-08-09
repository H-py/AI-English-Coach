"""AI 模块的 ORM 模型。

定义了支撑 AI 辅助学习的六张表：

* ``ai_conversations`` — 针对某篇文章与 AI 教练之间的聊天消息。
* ``ai_memories``      — 从较早的对话消息中提取并压缩的长期记忆摘要。
* ``user_profiles``    — 由累积记忆推导出的、AI 生成的学习者画像。
* ``ai_activities``    — 用户阅读期间的各种 AI 交互活动记录。
* ``reading_summaries`` — 某次阅读会话的 AI 生成总结。
* ``reading_quizzes``   — 某次阅读会话的 AI 生成练习题及答题结果。

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
    UniqueConstraint,
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

    ``history_id`` 将对话消息关联到具体的阅读会话，使每次阅读的问答
    记录可以被独立提取用于生成阅读总结。
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
    history_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("reading_histories.id"),
        index=True,
        nullable=True,
        default=None,
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


class AiActivity(Base):
    """用户在某次阅读会话中的 AI 交互活动记录。

    每次 AI 交互（查询单词、分析句子、翻译句子、段落摘要、问答）都会
    记录一条活动日志，关联到具体的阅读会话（``history_id``）。这些
    活动数据用于生成阅读总结，帮助用户回顾本次阅读的学习行为。

    ``activity_type`` 取值：``explain_word``、``analyze_sentence``、
    ``translate_sentence``、``paragraph_summary``、``chat``。
    ``content`` 存储用户输入的原始文本（如查询的单词、分析的句子等）。
    """

    __tablename__ = "ai_activities"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True, nullable=False
    )
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("articles.id"), index=True, nullable=False
    )
    history_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("reading_histories.id"),
        index=True,
        nullable=True,
        default=None,
    )
    activity_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<AiActivity id={self.id} type={self.activity_type!r}>"


class ReadingSummary(Base):
    """某次阅读会话的 AI 生成总结。

    每个阅读会话（``history_id``）最多保留一条总结——重新生成会覆盖
    旧的。总结基于用户在本次阅读中的 AI 交互活动（查词、分析句子、
    问答等）和阅读时长，由 LLM 生成。

    ``activity_stats`` 是 JSON 对象，存储各类活动的统计数据，例如
    ``{"word_count": 5, "sentence_count": 3, "chat_count": 4,
    "duration_seconds": 600}``。
    """

    __tablename__ = "reading_summaries"
    __table_args__ = (
        UniqueConstraint(
            "history_id", name="uq_reading_summaries_history"
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True, nullable=False
    )
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("articles.id"), nullable=False
    )
    history_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("reading_histories.id"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    activity_stats: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<ReadingSummary id={self.id} history_id={self.history_id}>"


class ReadingQuiz(Base):
    """某次阅读会话的 AI 生成练习题及答题结果。

    每个阅读会话可以有多份练习题（用户可以多次练习）。``questions``
    是 JSON 数组，每个元素包含题目、选项、正确答案和解析。
    ``user_answers`` 在用户提交前为 ``None``，提交后存储用户的答题
    结果及判分信息。

    ``questions`` 结构示例::

        [
            {
                "id": 1,
                "question": "What is the main idea?",
                "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
                "correct_answer": "B",
                "explanation": "..."
            }
        ]

    ``user_answers`` 结构示例::

        [
            {"question_id": 1, "user_answer": "B", "is_correct": true}
        ]
    """

    __tablename__ = "reading_quizzes"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True, nullable=False
    )
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("articles.id"), nullable=False
    )
    history_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("reading_histories.id"), nullable=False
    )
    questions: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    user_answers: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, default=None
    )
    score: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=None
    )
    total: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<ReadingQuiz id={self.id} history_id={self.history_id}>"
