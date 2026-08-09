"""文章 ORM 模型与难度枚举。

基于 CEFR（欧洲语言共同参考框架）能力等级定义了 ``articles`` 表以及
:class:`Difficulty` 枚举。该模型采用 SQLAlchemy 2.0 的 ``Mapped`` /
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
    """CEFR（欧洲语言共同参考框架）能力等级。

    范围从 A1（初学者）到 C2（精通）。用于标注文章难度，
    以便读者找到与自己水平匹配的内容。
    """

    a1 = "a1"
    a2 = "a2"
    b1 = "b1"
    b2 = "b2"
    c1 = "c1"
    c2 = "c2"


class Article(Base):
    """供学习者阅读的文章。

    存储文章的完整正文，以及标题、摘要、难度等级、字数、预计阅读时长、
    封面图、标签和浏览统计等元数据。``tags`` 列使用 ``JSON`` 类型来
    存储字符串标签列表。
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
        Enum(Difficulty),
        nullable=False,
        default=Difficulty.b1,
        server_default="b1",
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
