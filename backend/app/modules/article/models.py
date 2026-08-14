"""文章 ORM 模型与难度枚举。

定义了 ``articles`` 表、:class:`Difficulty` 难度枚举（1-5 星）以及
四六级真题类型。该模型采用 SQLAlchemy 2.0 的 ``Mapped`` /
``mapped_column`` 风格，并注册到共享的 :class:`~app.core.database.Base` 上，
以便 Alembic 自动生成迁移时能够发现它。
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Difficulty(enum.Enum):
    """文章难度，以 1-5 星表示。

    星级越高表示阅读难度越大。枚举值存储为字符串 ``"1"`` 到 ``"5"``，
    与数据库中的 ``difficulty`` 枚举类型取值一致。
    """

    one = "1"
    two = "2"
    three = "3"
    four = "4"
    five = "5"


class Article(Base):
    """供学习者阅读的文章。

    存储文章的完整正文，以及标题、摘要、难度星级、四六级真题类型、字数、
    预计阅读时长、封面图、标签和浏览统计等元数据。``tags`` 列使用
    ``JSON`` 类型来存储字符串标签列表。
    """

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None
    )
    source: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None
    )
    difficulty: Mapped[Difficulty] = mapped_column(
        Enum(Difficulty, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=Difficulty.three,
        server_default="3",
    )
    # 四六级真题类型：'cet4'（四级）/ 'cet6'（六级），NULL 表示非真题。
    cet_type: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, default=None
    )
    word_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    reading_time: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=None
    )
    cover_url: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True, default=None
    )
    tags: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    view_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
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
        return f"<Article id={self.id} title={self.title!r}>"
