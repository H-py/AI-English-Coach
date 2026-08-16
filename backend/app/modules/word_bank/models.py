"""词库模块的 ORM 模型与等级常量。

支撑分级单词知识库的两张表：

* ``word_bank``        — 词库单词（小写原形 + 音标 + 中文释义）。
* ``word_bank_levels`` — 单词与等级的归属（多对多，一个词可属多个等级，
  因为四级、六级、考研词高度重叠）。

等级以字符串存储（与文章 ``cet_type`` 同风格），便于拓展新等级
（雅思/托福/GRE 等 = 新增枚举值 + 导入数据），无需数据库枚举迁移。
"""

import enum
from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WordLevel(enum.Enum):
    """词汇等级常量。

    值即数据库 ``word_bank_levels.level`` 中存储的字符串。新增等级时
    在此追加枚举值并导入对应词表即可。
    """

    cet4 = "cet4"
    cet6 = "cet6"
    kaoyan = "kaoyan"


class WordBank(Base):
    """词库中的单词（小写原形，含音标与中文释义）。"""

    __tablename__ = "word_bank"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    word: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    phonetic: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None
    )
    meaning: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<WordBank id={self.id} word={self.word!r}>"


class WordBankLevel(Base):
    """词库单词的等级归属（``word_id`` + ``level`` 联合主键）。"""

    __tablename__ = "word_bank_levels"

    word_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("word_bank.id", ondelete="CASCADE"),
        primary_key=True,
    )
    level: Mapped[str] = mapped_column(String(20), primary_key=True, index=True)

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<WordBankLevel word_id={self.word_id} level={self.level!r}>"
