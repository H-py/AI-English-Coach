"""阅读模块的 ORM 模型与掌握程度枚举。

定义了支撑阅读功能的三张表：

* ``word_collections``     — 学习者在阅读时收藏的单词。
* ``sentence_collections`` — 学习者在阅读时收藏的句子。
* ``reading_histories``    — 每篇文章的阅读会话记录。

所有模型均采用 SQLAlchemy 2.0 的 ``Mapped`` / ``mapped_column`` 风格，
并注册到共享的 :class:`~app.core.database.Base` 上，以便 Alembic
自动生成迁移时能够发现它们。
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MasteryLevel(enum.Enum):
    """学习者对所收藏单词的掌握程度。

    从 ``new``（刚收藏）依次递进到 ``learning``、``familiar``，
    最终到 ``mastered``。该值由学习者手动推进，或由未来的间隔重复
    逻辑自动推进。
    """

    new = "new"
    learning = "learning"
    familiar = "familiar"
    mastered = "mastered"


class WordCollection(Base):
    """学习者收藏的单词，附带上下文与 AI 解释。

    每个 (用户, 单词) 组合都是唯一的：再次收藏同一个单词时，会更新
    已存储的上下文和解释，而不会创建重复记录。``mastery_level`` 和
    ``study_count`` 跟踪学习者对该单词的学习进度。
    """

    __tablename__ = "word_collections"
    __table_args__ = (
        UniqueConstraint("user_id", "word", name="uq_word_collections_user_word"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True, nullable=False
    )
    word: Mapped[str] = mapped_column(String(255), nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False)
    article_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("articles.id"), nullable=True, default=None
    )
    ai_explanation: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None
    )
    short_meaning: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None
    )
    mastery_level: Mapped[MasteryLevel] = mapped_column(
        Enum(MasteryLevel),
        nullable=False,
        default=MasteryLevel.new,
        server_default="new",
    )
    study_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_studied_at: Mapped[Optional[datetime]] = mapped_column(
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
        return f"<WordCollection id={self.id} word={self.word!r}>"


class SentenceCollection(Base):
    """学习者收藏的句子，可选附带个人备注。"""

    __tablename__ = "sentence_collections"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True, nullable=False
    )
    sentence: Mapped[str] = mapped_column(Text, nullable=False)
    article_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("articles.id"), nullable=True, default=None
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<SentenceCollection id={self.id}>"


class ReadingHistory(Base):
    """某篇文章的阅读会话记录（每用户每文章唯一）。

    每个用户对每篇文章只保留一条阅读历史记录（``user_id`` + ``article_id``
    唯一约束），确保阅读历史界面中同一篇文章只显示一张卡片。每次重新
    阅读时，会更新 ``started_at`` 为当前时间并递增 ``read_count``，
    ``ended_at`` 和 ``duration_seconds`` 被重置，等待本次会话结束时
    重新填写。

    AI 活动日志（``ai_activities``）和对话消息（``ai_conversations``）
    通过 ``history_id`` 关联到此记录，但在生成阅读总结时，会额外按
    ``created_at >= started_at`` 过滤，确保只统计本次会话的数据。
    """

    __tablename__ = "reading_histories"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "article_id", name="uq_reading_histories_user_article"
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True, nullable=False
    )
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("articles.id"), index=True, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    duration_seconds: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=None
    )
    read_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<ReadingHistory id={self.id} article_id={self.article_id}>"
