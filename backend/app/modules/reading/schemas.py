"""阅读模块的 Pydantic 模式（schema）。

描述了单词和句子收藏、以及阅读历史的传输数据结构。
采用 Pydantic v2 风格，使用 ``model_config`` / ``ConfigDict``，并在
读取类模式上启用 ``from_attributes``，以便直接从 ORM 实例构建。
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.modules.reading.models import MasteryLevel


# ---- 单词收藏模式 -----------------------------------------------------------


class WordCollectionCreate(BaseModel):
    """保存（upsert）收藏单词的载荷。

    ``article_id``、``ai_explanation`` 和 ``short_meaning`` 是可选的，
    因为学习者可能从文章以外的来源收藏单词，或在 AI 解释尚未生成
    之前就收藏。``short_meaning`` 为单词的简短释义，供生词本卡片
    列表直接展示。
    """

    word: str = Field(min_length=1, max_length=255)
    context: str
    article_id: Optional[int] = None
    ai_explanation: Optional[str] = None
    short_meaning: Optional[str] = None


class WordCollectionOut(BaseModel):
    """返回给客户端的收藏单词的完整表示。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    word: str
    context: str
    article_id: Optional[int] = None
    ai_explanation: Optional[str] = None
    short_meaning: Optional[str] = None
    mastery_level: MasteryLevel
    study_count: int
    last_studied_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    # 派生字段：该词在分级词库中归属的等级（如 ["cet4", "kaoyan"]）。
    # 由服务层批量查询词库后填充，ORM 序列化时默认为空列表。
    levels: list[str] = Field(default_factory=list)


class WordCollectionUpdate(BaseModel):
    """收藏单词掌握情况的部分更新载荷。

    两个字段都是可选的，以便客户端可以只更新掌握程度、只更新学习次数，
    或同时更新两者。
    """

    mastery_level: Optional[MasteryLevel] = None
    study_count: Optional[int] = None


class WordListResponse(BaseModel):
    """带总数统计的收藏单词分页列表。"""

    items: list[WordCollectionOut]
    total: int


class VocabularyPlanOut(BaseModel):
    """一次背诵方案：有序的单词序列 + 背诵建议 + 来源标记。"""

    words: list[WordCollectionOut]
    note: Optional[str] = None
    total: int
    generated_by: Literal["agent", "rule"]


# ---- 句子收藏模式 -----------------------------------------------------------


class SentenceCollectionCreate(BaseModel):
    """保存收藏句子的载荷。"""

    sentence: str
    article_id: Optional[int] = None
    note: Optional[str] = None


class SentenceCollectionOut(BaseModel):
    """返回给客户端的收藏句子的完整表示。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    sentence: str
    article_id: Optional[int] = None
    note: Optional[str] = None
    created_at: datetime


class SentenceCollectionUpdate(BaseModel):
    """收藏句子备注的部分更新载荷。

    只有 ``note`` 可更新；句子文本一旦保存即不可变。
    """

    note: Optional[str] = None


class SentenceListResponse(BaseModel):
    """带总数统计的收藏句子分页列表。"""

    items: list[SentenceCollectionOut]
    total: int


# ---- 阅读历史模式 -----------------------------------------------------------


class ReadingHistoryCreate(BaseModel):
    """开启新阅读会话的载荷。"""

    article_id: int


class ReadingHistoryOut(BaseModel):
    """返回给客户端的阅读历史记录的完整表示。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    article_id: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    read_count: int = 1
    created_at: datetime


class ReadingHistoryUpdate(BaseModel):
    """结束阅读会话的部分更新载荷。

    通常学习者停止阅读时会同时提供 ``ended_at`` 和 ``duration_seconds``，
    但两者都是可选的，以保持载荷的灵活性。
    """

    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None


class ReadingHistoryListResponse(BaseModel):
    """带总数统计的阅读历史记录分页列表。"""

    items: list[ReadingHistoryOut]
    total: int


class ReadingHistoryWithArticleOut(BaseModel):
    """附加了文章标题的阅读历史记录。

    由仓库层 :func:`list_histories_with_article` 返回的
    ``(ReadingHistory, article_title)`` 元组构建而成。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    article_id: int
    article_title: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    read_count: int = 1
    created_at: datetime


class ReadingHistoryWithArticleListResponse(BaseModel):
    """带文章标题的阅读历史记录分页列表。"""

    items: list[ReadingHistoryWithArticleOut]
    total: int
